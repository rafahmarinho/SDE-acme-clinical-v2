---
name: t84-test-page-level-authorization
description: Test that every authenticated ACME Clinical screen and API route (wards, patients, live monitoring, alarms, devices, thresholds, reports, staff, simulation) refuses access without a valid session, including alternative paths.
---

# T84: Test page-level authorization

**Category:** CODE_FIX
**SD Elements:** [T84](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T84/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: "ward view, patient list and detail, live monitoring, alarms, devices,")
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
A React SPA typically "protects" pages with a client-side route guard, while the FastAPI endpoints that feed those pages accept anonymous requests. Clearing the session and calling `/patients` directly, or loading the deep link of a report file, returns data.

**Secure Implementation Pattern:**
```python
# backend/tests/test_unauthenticated_access.py
import pytest
from app.main import app
from app.core.security import PUBLIC_ROUTES  # e.g. {"/health", "/auth/password-reset"}

PROTECTED = [r for r in app.routes
             if getattr(r, "methods", None) and r.path not in PUBLIC_ROUTES]

@pytest.mark.parametrize("route", PROTECTED, ids=lambda r: f"{sorted(r.methods)}{r.path}")
async def test_requires_auth(client, route):
    path = route.path.replace("{", "").replace("}", "")  # dummy ids
    for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Bearer "}):
        r = await client.request(sorted(route.methods)[0], path, headers=headers)
        assert r.status_code == 401, r.text

@pytest.mark.parametrize("alt", ["/Patients", "/patients/", "/api/../patients", "/docs", "/openapi.json"])
async def test_alternative_paths(client, alt):
    assert (await client.get(alt)).status_code in (401, 404)
```

**Implementation Guidance:**
- Generate the test list from `app.routes` so every new router in `backend/app/routers/` is covered automatically; only `PUBLIC_ROUTES` (T373) are exempt.
- Test with no token, malformed token, expired token and a token signed with another key.
- Cover alternative access paths: trailing slashes, case variants, FastAPI `/docs` and `/openapi.json` (disable in production via `backend/app/core/config.py`), Supabase Storage public URLs for reports and files.
- For the frontend, add a Vitest/Playwright check that loading `/patients/:id` without a session redirects to `/login` and issues no data request that succeeds.
- Reference: SD Elements guidance for T84.

**Success Criteria:**
- [ ] Every non-whitelisted route returns 401 without valid credentials in `backend/tests/test_unauthenticated_access.py`.
- [ ] `/docs` and `/openapi.json` are unavailable in production configuration.
- [ ] Storage objects (reports, files) cannot be fetched anonymously.

**Status:** Applied
