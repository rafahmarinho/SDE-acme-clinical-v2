---
name: t93-test-that-sessions-expire-upon-logout
description: Tests proving that after logout in ACME Clinical the old Supabase access and refresh tokens are rejected by the FastAPI API and Supabase, and that the browser Back button does not reveal patient data.
---

# T93: Test that sessions expire upon logout

**Category:** CODE_FIX
**SD Elements:** [T93](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T93/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
The PRD only asks for login and the main flows to be checked. A team would confirm the logout button returns to the login screen, but not that the tokens are dead server-side. Since ACME Clinical sends Bearer tokens (not cookies), the SD Elements "replay stored session cookies" step translates to replaying the captured `Authorization: Bearer` access token and refresh token.

**Secure Implementation Pattern:**
```python
# backend/tests/test_logout.py
async def test_access_token_rejected_after_logout(api, supabase_login):
    s = await supabase_login("demo.nurse@acme-clinical.test")
    await api.post("/auth/session", headers=s.auth_header)
    assert (await api.get("/patients", headers=s.auth_header)).status_code == 200

    r = await api.post("/auth/logout", headers=s.auth_header)
    assert r.status_code == 204
    assert r.headers["cache-control"] == "no-store"

    # replay captured credentials (JWT not yet expired)
    r = await api.get("/patients", headers=s.auth_header)
    assert r.status_code == 401 and "patients" not in r.text.lower()
    assert (await supabase_refresh(s.refresh_token)).status_code in (400, 401)
    # direct Supabase access through RLS is also closed
    assert await supabase_rest_select("patients", s.access_token) == []

async def test_logout_is_not_a_get(api, supabase_login):
    s = await supabase_login("demo.nurse@acme-clinical.test")
    assert (await api.get("/auth/logout", headers=s.auth_header)).status_code == 405

async def test_authenticated_responses_not_cacheable(api, nurse):
    r = await api.get("/patients/1", headers=nurse.auth_header)
    assert "no-store" in r.headers["cache-control"]
```

**Implementation Guidance:**
- Server-side test (above) in `backend/tests/test_logout.py`, using the fixtures from `backend/tests/conftest.py` against a local Supabase stack.
- Browser test (Playwright in `frontend/tests/e2e/logout.spec.ts`, or documented manual check): log in as the demo nurse, open a patient detail, log out, then press Back and paste the patient URL into the address bar. The test fails if any patient name, vital sign or observation is rendered; the app must redirect to `/login`.
- In the same browser test, assert that `sessionStorage`/`localStorage` no longer contain the `sb-<project-ref>-auth-token` key and that the Realtime WebSocket is closed.
- Use DevTools to capture the `Authorization` header before logout and replay it with curl after logout; expect `401`.
- Reference: SD Elements guidance for T93.

**Success Criteria:**
- [ ] Replayed access token after logout returns `401` and no private data.
- [ ] Replayed refresh token is rejected by Supabase Auth.
- [ ] Back button / direct URL after logout shows the login screen, never cached patient data.
- [ ] `GET /auth/logout` returns `405`.

**Status:** Pending
