---
name: t92-test-absolute-session-timeout
description: Tests proving that an ACME Clinical session is terminated at its absolute lifetime even when the user stays active and tokens keep refreshing.
---

# T92: Test absolute session timeout

**Category:** CODE_FIX
**SD Elements:** [T92](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T92/)
**Priority:** 3/10 · **Phase:** testing

**Spec Context:**
> "devem aparecer nas telas e continuar salvos após recarregar a aplicação."
> (EN: must appear on the screens and remain saved after reloading the application.)
> Source: specs/PRD.md, line 45

**What the spec implies (naive approach):**
Tests would check that data survives a reload, and would likely also confirm the user stays logged in after reload. No test would keep a session busy for a full shift to check that it eventually ends, so an unbounded refresh-token chain would pass.

**Secure Implementation Pattern:**
```python
# backend/tests/test_absolute_timeout.py
async def test_active_session_expires_at_absolute_limit(api, nurse, freeze_time):
    limit = timedelta(hours=settings.absolute_timeout_hours)
    elapsed = timedelta()
    while elapsed < limit - timedelta(minutes=5):        # stay active: heartbeat every 5 min
        freeze_time.tick(minutes=5); elapsed += timedelta(minutes=5)
        assert (await api.post("/auth/heartbeat", headers=nurse.auth_header)).status_code == 204
    freeze_time.tick(minutes=10)
    r = await api.get("/patients", headers=nurse.auth_header)
    assert r.status_code == 401 and r.json()["error"] == "session_expired"

async def test_refresh_does_not_extend_lifetime(api, nurse, freeze_time):
    freeze_time.tick(hours=settings.absolute_timeout_hours + 1)
    refreshed = await nurse.refresh()            # Supabase may still issue a token if timebox not set
    r = await api.get("/patients", headers=refreshed.auth_header)
    assert r.status_code == 401
```

**Implementation Guidance:**
- Implement in `backend/tests/test_absolute_timeout.py` using simulated time (inject a clock into `backend/app/core/security.py`); the refreshed token keeps the same `session_id`, so the server must still reject it.
- Manual/staging check per SD Elements: a small script (`backend/tests/manual/keepalive.py`) logs in, then calls `GET /patients` and the Supabase refresh endpoint every 5 minutes for the configured limit (for example 12 hours), logging the first non-200 response. The test fails if access continues past the limit.
- Also verify the Supabase "Time-boxed user sessions" setting by checking that the refresh grant fails after the timebox.
- Reference: SD Elements guidance for T92.

**Success Criteria:**
- [ ] Continuous activity cannot extend a session past the absolute limit.
- [ ] Refreshed tokens of an expired session are rejected by the API.
- [ ] Staging keep-alive script documents the exact cut-off time.

**Status:** Applied
