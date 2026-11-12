---
name: t90-test-idle-session-timeout
description: Tests verifying that ACME Clinical locks the UI and rejects API calls after the configured idle period, that background Realtime traffic and token refreshes do not count as activity, and that unlocking requires re-authentication.
---

# T90: Test idle session timeout

**Category:** CODE_FIX
**SD Elements:** [T90](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T90/)
**Priority:** 3/10 · **Phase:** testing

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
Following the PRD, tests would confirm the live monitoring screen keeps updating. Nobody would leave a session idle for 15-30 minutes to see if it is locked, and a design where background refreshes keep the session alive forever would pass every functional test.

**Secure Implementation Pattern:**
```python
# backend/tests/test_idle_timeout.py
async def test_api_rejects_idle_session(api, nurse, db, freeze_time):
    await api.post("/auth/heartbeat", headers=nurse.auth_header)
    freeze_time.tick(minutes=settings.idle_timeout_minutes + 1)
    r = await api.get("/patients", headers=nurse.auth_header)          # data request, not a heartbeat
    assert r.status_code == 401 and r.json()["error"] == "session_idle"
    assert (await api.post("/auth/heartbeat", headers=nurse.auth_header)).status_code == 401  # no resurrection

async def test_data_requests_do_not_count_as_activity(api, nurse, freeze_time):
    for _ in range(4):                                  # simulate background polling every 5 min
        freeze_time.tick(minutes=5)
        await api.get("/alarms?status=active", headers=nurse.auth_header)
    assert (await api.get("/patients", headers=nurse.auth_header)).status_code == 401
```
```typescript
// frontend/src/hooks/useIdleLock.test.ts (vitest)
it("locks after idle period and ignores realtime updates", () => {
  vi.useFakeTimers(); const onLock = vi.fn();
  renderHook(() => useIdleLock(15 * 60_000, onLock));
  emitRealtimeVitals();                              // must not reset the timer
  vi.advanceTimersByTime(15 * 60_000);
  expect(onLock).toHaveBeenCalledOnce();
});
```

**Implementation Guidance:**
- Backend tests in `backend/tests/test_idle_timeout.py`; use `time-machine`/`freezegun` (or inject a clock into `backend/app/core/security.py`) instead of waiting real time.
- Frontend unit test in `frontend/src/hooks/useIdleLock.test.ts` with vitest fake timers; add a Playwright test that sets a 1-minute idle value via an admin setting in a test environment and verifies the lock screen hides patient names and vitals.
- Manual check per SD Elements on the deployed app: log in, open live monitoring, do not touch the workstation for the configured period, then click a patient. The test fails if data is shown without re-entering the password. Clear cache before testing if needed.
- Reference: SD Elements guidance for T90.

**Success Criteria:**
- [ ] API returns `401 session_idle` after the idle window regardless of background traffic.
- [ ] UI locks at the configured time and unlock requires the password.
- [ ] Tests run in CI with simulated time.

**Status:** Applied
