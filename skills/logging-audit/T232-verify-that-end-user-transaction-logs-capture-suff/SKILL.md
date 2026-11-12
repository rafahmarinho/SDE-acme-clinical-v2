---
name: t232-verify-that-end-user-transaction-logs-capture-suff
description: Tests that every ACME Clinical clinical transaction (alarm acknowledgement, observation, threshold change, monitor-bed binding, maintenance, staff change, simulation reset) produces an audit row with user ID, UTC timestamp, source IP, description and error code.
---

# T232: Verify that end-user transaction logs capture sufficient information

**Category:** CODE_FIX
**SD Elements:** [T232](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T232/)
**Priority:** 3/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados."
> (EN: choose scenarios, advance the simulation, view events and reset the data.)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
The "events" list would likely show only simulation events (scenario, time, monitor). Without a test, rows would miss who performed the action, from where, or whether it failed, making clinical actions unauditable.

**Secure Implementation Pattern:**
```python
# backend/tests/test_audit_completeness.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

TRANSACTIONS = [
    ("post", "/alarms/{alarm_id}/acknowledge", None, "alarm.acknowledge"),
    ("post", "/observations", {"patient_id": "{patient_id}", "text": "Stable"}, "observation.create"),
    ("put", "/thresholds/{patient_id}", {"spo2_low": 90}, "threshold.update"),
    ("post", "/monitors/{monitor_id}/bind", {"bed_id": "{bed_id}"}, "monitor.bind"),
]

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body,action", TRANSACTIONS)
async def test_transaction_audited(method, path, body, action, ids, nurse, audit_rows):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        payload = {k: v.format(**ids) if isinstance(v, str) else v for k, v in (body or {}).items()}
        await c.request(method, path.format(**ids), json=payload or None,
                        headers={"Authorization": f"Bearer {nurse.token}",
                                 "X-Forwarded-For": "203.0.113.7"})
    row = audit_rows(action)[-1]
    assert row["actor_id"] == nurse.id
    assert row["occurred_at"].tzinfo is not None and row["occurred_at"].microsecond is not None
    assert row["source_ip"] == "203.0.113.7"
    assert row["action"] == action and row["outcome"] in ("success", "failure")
    assert "error_code" in row
```

**Implementation Guidance:**
- Enumerate all end-user transactions from the PRD: alarm acknowledgement, observations, threshold settings, monitor-bed binding, maintenance records, staff/role management, simulation scenario/advance/reset, report generation, file upload.
- For each, call the endpoint and query `audit_events` (via a test DB or Supabase local stack) asserting `actor_id`, `occurred_at` (timestamptz, ms), `source_ip`, `action`, `target_type/target_id`, `outcome`, `error_code`.
- Include failure cases (e.g. acknowledging an already-closed alarm) and assert `outcome = failure` with an error code.
- On Vercel, source IP comes from `x-forwarded-for`/`x-real-ip` set by the platform; test the extraction helper.
- Reference: SD Elements guidance for T232.

**Success Criteria:**
- [ ] Parametrized test covers every PRD transaction listed above.
- [ ] Test fails if any required field is null for a transaction.
- [ ] Failure outcomes are audited with an error code.

**Status:** Applied
