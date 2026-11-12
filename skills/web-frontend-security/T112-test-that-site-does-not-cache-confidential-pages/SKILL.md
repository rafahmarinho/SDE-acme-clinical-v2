---
name: t112-test-that-site-does-not-cache-confidential-pages
description: Automated and manual tests verifying that ACME Clinical API responses with patient data and the authenticated SPA shell are served with Cache-Control no-store (plus Pragma/Expires) so clinical data is not retained in browser or proxy caches.
---

# T112: Test that site does not cache confidential pages

**Category:** CODE_FIX
**SD Elements:** [T112](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T112/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Observations, patient details and alarm history are returned by FastAPI as JSON and rendered by the React SPA. If nobody tests the caching headers, a regression (e.g. a router returning a custom `Response` or a Vercel config change) can silently make patient data cacheable on shared ward workstations.

**Secure Implementation Pattern:**
```python
# backend/tests/test_cache_headers.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

CONFIDENTIAL = ["/api/patients", "/api/patients/demo-1", "/api/alarms",
                "/api/patients/demo-1/observations", "/api/reports"]

@pytest.mark.anyio
@pytest.mark.parametrize("path", CONFIDENTIAL)
async def test_confidential_responses_are_not_cacheable(path, auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        r = await c.get(path, headers=auth_headers)
    cc = r.headers.get("cache-control", "").lower()
    assert "no-store" in cc
    assert "must-revalidate" in cc
    assert r.headers.get("pragma") == "no-cache"
    assert r.headers.get("expires") in {"0", "-1"}

@pytest.mark.anyio
async def test_error_responses_are_not_cacheable():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        r = await c.get("/api/patients")  # no token -> 401
    assert "no-store" in r.headers.get("cache-control", "")
```

**Implementation Guidance:**
- Add the test above under `backend/tests/` with an `auth_headers` fixture (in `conftest.py`) that issues a test JWT for a nurse role; it verifies the control from T64.
- Manual check against the deployed URLs: `curl -sI https://<api>.vercel.app/api/patients -H "Authorization: Bearer <token>"` and `curl -sI https://<web>.vercel.app/` and confirm `Cache-Control: no-store` (HTTP/1.1) and `Pragma: no-cache`/`Expires` (HTTP/1.0 compatibility).
- The test fails if only `no-cache` is present without `no-store`.
- Browser check: log in, open a patient detail, log out, press Back; patient data must not be redisplayed from cache.
- Reference: SD Elements guidance for T112.

**Success Criteria:**
- [ ] `backend/tests/test_cache_headers.py` passes in CI for all confidential endpoints and for error responses.
- [ ] Manual curl check against the Vercel deployments shows `no-store` for the API and `index.html`.
- [ ] After logout, browser Back navigation does not show cached patient data.

**Status:** Applied
