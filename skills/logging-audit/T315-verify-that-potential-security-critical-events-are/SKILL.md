---
name: t315-verify-that-potential-security-critical-events-are
description: Tests that ACME Clinical's security log captures detection points such as repeated failed logins, unsupported HTTP methods, direct object access attempts on patients/alarms and forced browsing to role-restricted routes, with a consistent UTC time reference.
---

# T315: Verify that potential security-critical events are logged

**Category:** CODE_FIX
**SD Elements:** [T315](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T315/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: filters, loading states and error messages. Adapt navigation to the user profiles)
> Source: specs/PRD.md, line 13

**What the spec implies (naive approach):**
Navigation is adapted per role in the React UI, so developers assume users cannot reach restricted actions and never test or log direct API calls (e.g. a nurse calling `/staff` or `/simulation/reset`, or iterating patient IDs). Attack attempts go unrecorded.

**Secure Implementation Pattern:**
```python
# backend/tests/test_security_events.py
import json, logging, pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

def sec_events(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "acme.security"]

@pytest.mark.asyncio
async def test_detection_points_logged(caplog, nurse_token, other_ward_patient_id):
    caplog.set_level(logging.INFO, logger="acme.security")
    h = {"Authorization": f"Bearer {nurse_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        for _ in range(5):                                            # AE2/AE3
            await c.post("/auth/login", json={"email": "x@acme.test", "password": "bad"})
        await c.delete("/alarms/1", headers=h)                       # RE2 unsupported method
        await c.post("/simulation/reset", headers=h)                 # ACE3 forced browsing
        await c.get(f"/patients/{other_ward_patient_id}", headers=h) # ACE1 IDOR attempt
        await c.post("/observations", headers=h, json={"text": "<script>x</script>", "extra": 1})  # AE10
    names = [e["event"] for e in sec_events(caplog)]
    for expected in ["login_failed", "method_not_allowed", "authz_denied", "input_validation_failed"]:
        assert expected in names
    assert all(e["ts"].endswith("+00:00") for e in sec_events(caplog))   # UTC everywhere
```

**Implementation Guidance:**
- Implement the test above in `backend/tests/` using the event names emitted by T45 (`core/logging.py`).
- Map relevant detection points: AE2/AE3 (failed/high-rate logins), RE2–RE4 (405 handler in `main.py` must emit `method_not_allowed`), ACE1–ACE3 (403/404 on patients, alarms, monitors outside the user's scope or role), AE10 (Pydantic `extra="forbid"` rejection), IE1 (script payloads in observations), FIO1/FIO2 (oversized or many uploads), STE3 (repeated simulation resets).
- Verify each logged entry has UTC timestamp with milliseconds, user_id, source IP, event and outcome; verify Postgres `now()` and backend use UTC (`timestamptz`).
- Login detection points depend on Supabase Auth: if login is done client-side directly with Supabase, document that auth failure events come from Supabase Auth logs and test via a backend login proxy or log review instead.
- Reference: SD Elements guidance for T315.

**Success Criteria:**
- [ ] Pytest covers at least AE2, RE2, ACE1, ACE3, AE10 and FIO1 and passes.
- [ ] All security events carry UTC ISO-8601 timestamps with milliseconds.
- [ ] Gaps (e.g. Supabase-side auth events) documented with where they are observed.

**Status:** Pending
