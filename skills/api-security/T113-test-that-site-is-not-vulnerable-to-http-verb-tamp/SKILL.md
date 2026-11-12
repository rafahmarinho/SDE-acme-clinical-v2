---
name: t113-test-that-site-is-not-vulnerable-to-http-verb-tamp
description: Tests verifying that ACME Clinical's FastAPI routes cannot be reached without authentication by changing the HTTP verb (arbitrary verbs, HEAD instead of GET, method-override headers).
---

# T113: Test that site is not vulnerable to HTTP verb tampering

**Category:** CODE_FIX
**SD Elements:** [T113](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T113/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "Adapte a navegação aos perfis de"
> (EN: Adapt the navigation to the [user] profiles)
> Source: specs/PRD.md, line 13

> "Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: Have profiles for nurse, physician, biomedical technician and administrator.)
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
Role-based protection is typically attached per decorated route. If a developer adds an auth check in middleware only for `GET`/`POST`, registers a `HEAD` or catch-all handler without the auth dependency, or honours `X-HTTP-Method-Override`, a different verb can reach protected staff, threshold or simulation-reset logic without a valid session or role.

**Secure Implementation Pattern:**
```python
# backend/tests/test_verb_tampering.py
import pytest

PROTECTED = [r for r in app.routes if isinstance(r, APIRoute) and r.path not in ("/health",)]

@pytest.mark.parametrize("route", PROTECTED, ids=lambda r: r.path)
@pytest.mark.parametrize("verb", ["PWRLWA", "TRACE", "HEAD", "PUT", "OPTIONS"])
async def test_unauthenticated_verb_tampering(api, route, verb):
    path = route.path.replace("{", "").replace("}", "")  # crude param fill -> e.g. /patients/id
    r = await api.request(verb, path.replace("id", "1"))
    assert r.status_code in (400, 401, 403, 404, 405), f"{verb} {route.path} -> {r.status_code}"
    assert r.status_code != 200 and not r.content.strip().startswith(b'{"items"')

async def test_head_does_not_bypass_auth(api):
    assert (await api.head("/patients")).status_code in (401, 405)

async def test_method_override_ignored(api, nurse, db):
    before = await db.fetchval("select count(*) from simulation_events")
    r = await api.get("/simulation/state", headers={**nurse.auth_header, "X-HTTP-Method-Override": "POST"})
    assert r.status_code == 400
    assert await db.fetchval("select count(*) from simulation_events") == before

async def test_role_enforced_for_every_verb(api, nurse):
    for verb in ("POST", "PATCH", "DELETE"):
        r = await api.request(verb, "/staff/1", headers=nurse.auth_header, json={})
        assert r.status_code in (403, 405)
```

**Implementation Guidance:**
- Implement `backend/tests/test_verb_tampering.py`, iterating the real route table from `backend/app/main.py` so new routes are covered automatically. `OPTIONS` without CORS preflight headers must not return data.
- For `HEAD`, also confirm no side effect occurred (check `simulation_events`, `alarm_acknowledgements` and audit tables before/after), per SD Elements step 3.
- Manual check with Burp/curl against staging: `curl -X PWRLWA https://<api>/patients` and `curl -I https://<api>/patients` without a token.
- Reference: SD Elements guidance for T113.

**Success Criteria:**
- [ ] No verb returns protected data without a valid session.
- [ ] HEAD never succeeds where GET would be denied, and causes no state change.
- [ ] Method-override headers are rejected; role checks apply to every verb.
- [ ] Tests run in CI.

**Status:** Pending
