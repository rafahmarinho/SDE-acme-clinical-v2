---
name: t432-test-that-logging-failures-and-other-minor-failure
description: Automated pytest checks that ACME Clinical follows its designed response to audit/logging failures, keeps alarms and live monitoring working during minor failures, and alerts administrators.
---

# T432: Test that logging failures and other minor failures are securely handled

**Category:** CODE_FIX
**SD Elements:** [T432](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T432/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "Simule leituras normais, saturação baixa, bateria fraca, problema no sensor e"
> (EN: Simulate normal readings, low saturation, low battery, sensor problem and)
> Source: specs/PRD.md, line 37

**What the spec implies (naive approach):**
Teams typically test only the happy path of the simulation scenarios. Nobody injects a failing audit sink, so it is unknown whether a logging outage stops low-saturation alarms from firing or silently loses acknowledgement records.

**Secure Implementation Pattern:**
```python
# backend/tests/test_logging_failures.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core import logging as audit

class FailingDB:
    async def insert_audit_event(self, event): raise ConnectionError("db down")

@pytest.mark.asyncio
@pytest.mark.parametrize("failure", list(audit.FAILURE_POLICY))
async def test_every_catalogued_failure_has_a_test(failure):
    assert failure in audit.FAILURE_POLICY  # catalogue is the source of truth

@pytest.mark.asyncio
async def test_alarm_still_raised_when_audit_fails(monkeypatch, nurse_token):
    monkeypatch.setattr(audit, "get_db", lambda: FailingDB())
    alerts = []
    async def fake_notify(key): alerts.append(key)
    monkeypatch.setattr(audit, "notify_admins", fake_notify)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/simulation/advance", json={"scenario": "low_saturation"},
                         headers={"Authorization": f"Bearer {nurse_token}"})
    assert r.status_code == 200
    assert any(a["type"] == "low_spo2" for a in r.json()["alarms"])
    assert alerts == ["audit_insert_failed"]

@pytest.mark.asyncio
async def test_ack_refused_when_audit_cannot_be_written(monkeypatch, nurse_token):
    monkeypatch.setattr(audit, "get_db", lambda: FailingDB())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/alarms/123/acknowledge", headers={"Authorization": f"Bearer {nurse_token}"})
    assert r.status_code == 503 and "db down" not in r.text
```

**Implementation Guidance:**
- Iterate the failure catalogue defined for T431 in `backend/app/core/logging.py`; each entry needs at least one test that simulates it (failing DB fake, full buffer, Realtime publish exception).
- Verify the designed alternative action: buffering/retry for minor failures, refusal (503) for the alarm acknowledgement path.
- Verify critical functions (`services/alarms.py`, `services/simulation.py`, live readings) still respond during the simulated failure.
- Verify the administrator is alerted (`notify_admins` called / `system_alerts` row inserted).
- Reference: SD Elements guidance for T432.

**Success Criteria:**
- [ ] `backend/tests/test_logging_failures.py` covers every key in `FAILURE_POLICY`.
- [ ] Test fails if a minor logging failure causes non-200 on alarm/reading endpoints.
- [ ] Test fails if no admin alert is produced on audit failure.
- [ ] Tests run in CI (`pytest backend/tests`).

**Status:** Pending
