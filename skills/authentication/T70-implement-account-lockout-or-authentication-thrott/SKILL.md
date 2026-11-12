---
name: t70-implement-account-lockout-or-authentication-thrott
description: Throttle and lock out failed authentication attempts by ACME Clinical system accounts, chiefly the simulated bedside monitors presenting device secrets, with database-backed, exponentially growing lock periods shared by all API instances.
---

# T70: Implement account lockout or authentication throttling for system accounts

**Category:** CODE_FIX
**SD Elements:** [T70](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T70/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "frequência cardíaca, saturação, respiração, pressão arterial e um traçado sintético de ECG."
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: heart rate, saturation, respiration, blood pressure and a synthetic ECG trace. Allow linking a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, lines 31-33

**What the spec implies (naive approach):**
Simulated monitors that push readings are system accounts identified by a monitor ID plus secret. A naive endpoint compares the secret on each request with no failure counter, or keeps an in-memory counter per Vercel function instance, so an attacker can brute-force a device secret and inject false vital signs or suppress alarms.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0006_auth.sql (verify_monitor_secret): failures are shared state in the DB
insert into private.device_auth_failures as f (monitor_id, failures) values (p_monitor, 1)
on conflict (monitor_id) do update
  set failures = f.failures + 1,
      -- exponential back-off: 1, 2, 4 ... minutes after 5 failures, capped at 24 h
      locked_until = case when f.failures + 1 >= 5
        then now() + least(interval '24 hours',
                           interval '1 minute' * power(2, f.failures + 1 - 5))
        else f.locked_until end,
      updated_at = now();
return false;
```
```python
# backend/app/services/device_auth.py - fail closed, same answer for "locked" and "wrong secret"
async def verify_in_db(conn, monitor_id: UUID, presented: str | None) -> None:
    ok = await fetch_val(conn, "select public.verify_monitor_secret(%s, %s)", (monitor_id, presented))
    if not ok:
        await record_event(None, "device_auth_failed", "monitor", str(monitor_id), outcome="denied")
        raise DeviceAuthError()
```

**Implementation Guidance:**
- Keep the counter in `private.device_auth_failures` (not in process memory) so every Vercel instance sees the same state; `verify_monitor_secret` in `supabase/migrations/0006_auth.sql` already locks for 15 minutes after 5 failures - make the lock period grow exponentially on repeated lockouts.
- Respond identically for "locked", "unknown monitor" and "wrong secret" in `backend/app/services/device_auth.py`; log each failure and each lockout through `backend/app/core/audit.py` and raise a `system_alerts` row for administrators.
- Rate-limit device and API-key authentication paths per source too (`backend/app/core/middleware.py` limiter) so one IP cannot cycle through monitor IDs.
- Provide an audited administrator unlock (pattern of `public.unlock_staff_account`) and reset the counter on successful authentication.
- Supabase service-role and database credentials are not brute-forceable through the app; their throttling is the Supabase platform's responsibility (see cloud-infrastructure skills).
- Reference: SD Elements guidance for T70.

**Success Criteria:**
- [ ] `backend/tests/test_authentication.py::test_device_verification_sql_is_hashed_and_throttled` also asserts the exponential back-off and the 24-hour cap.
- [ ] Pytest: 5 bad secrets lock the monitor; the correct secret is refused while locked; the response is identical to a wrong-secret response.
- [ ] Pytest: lockout produces an audit event and an admin alert; admin unlock is audited and admin-only.

**Status:** Applied
