---
name: t430-test-that-the-number-of-concurrent-sessions-for-ea
description: Automated tests verifying that ACME Clinical enforces per-role concurrent session limits on Supabase Auth sessions, revokes the oldest session when the limit is exceeded, and that the session management panel lists and terminates sessions correctly.
---

# T430: Test that the number of concurrent sessions for each account is limited

**Category:** CODE_FIX
**SD Elements:** [T430](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T430/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: Have profiles for nurse, physician, biomedical technician and administrator.)
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
Following the PRD, the team would test only that each role can log in and sees the right navigation. Nobody would check what happens when the same account signs in from several ward workstations, so a missing or broken concurrent-session limit (T429) would go unnoticed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_concurrent_sessions.py  (runs against a local Supabase: `supabase start`)
import pytest

@pytest.mark.parametrize("role,limit", [("administrator", 1), ("nurse", 2)])
async def test_oldest_session_revoked_when_limit_exceeded(api, supabase_login, role, limit):
    sessions = []
    for _ in range(limit + 1):
        s = await supabase_login(f"demo.{role}@acme-clinical.test")   # fresh Supabase session each time
        r = await api.post("/auth/session", headers=s.auth_header)
        assert r.status_code == 201
        sessions.append(s)

    oldest, newest = sessions[0], sessions[-1]
    r = await api.get("/patients", headers=oldest.auth_header)
    assert r.status_code == 401 and r.json()["error"] == "session_revoked"
    assert (await api.get("/patients", headers=newest.auth_header)).status_code == 200
    # refresh token of the revoked session must be dead at Supabase Auth as well
    assert (await supabase_refresh(oldest.refresh_token)).status_code in (400, 401)

async def test_user_can_list_and_terminate_own_sessions(api, supabase_login):
    a = await supabase_login("demo.nurse@acme-clinical.test"); await api.post("/auth/session", headers=a.auth_header)
    b = await supabase_login("demo.nurse@acme-clinical.test"); await api.post("/auth/session", headers=b.auth_header)
    listed = (await api.get("/auth/sessions", headers=b.auth_header)).json()["items"]
    assert {x["session_id"] for x in listed} >= {a.session_id, b.session_id}
    assert all({"created_at", "last_activity_at", "user_agent"} <= x.keys() for x in listed)
    assert (await api.delete(f"/auth/sessions/{a.session_id}", headers=b.auth_header)).status_code == 204
    assert (await api.get("/patients", headers=a.auth_header)).status_code == 401
```

**Implementation Guidance:**
- Create fixtures in `backend/tests/conftest.py`: an `httpx.AsyncClient` bound to `backend/app/main.py` (ASGI transport) and a `supabase_login` helper that calls the local Supabase Auth `token?grant_type=password` endpoint for seeded demo users (from `supabase/seed.sql`) and returns access token, refresh token and the decoded `session_id` claim.
- Verify the **maximum** per account type (administrator 1, other clinical roles 2, or whatever T429 configures in `backend/app/core/config.py`).
- Verify the **action** taken: the oldest session gets `401 session_revoked` from the API and its refresh token is rejected by Supabase Auth (row removed from `auth.sessions`).
- Add a race test: fire `limit + 3` concurrent `POST /auth/session` calls with `asyncio.gather` and assert at most `limit` sessions remain active.
- Verify the panel: list shows only the caller's sessions (a nurse cannot see or revoke another user's session: expect `404`), deletion works, and an administrator can revoke a staff member's sessions.
- Manual check (frontend): sign in on two browsers as the demo administrator; the first browser must show the "signed out on another device" message on its next API call.
- Reference: SD Elements guidance for T430.

**Success Criteria:**
- [ ] `backend/tests/test_concurrent_sessions.py` passes in CI against local Supabase.
- [ ] Exceeding the limit always revokes the oldest session (API 401 and refresh token rejected).
- [ ] Concurrency test never leaves more than the configured number of active sessions.
- [ ] Cross-user session listing/termination is denied.

**Status:** Applied
