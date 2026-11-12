---
name: t438-verify-that-log-reduction-and-report-generation-ca
description: Tests that ACME Clinical's Python audit report endpoint supports on-demand filtering and summarization of audit events without altering original records or their time ordering.
---

# T438: Verify that log reduction and report generation capabilities exist

**Category:** CODE_FIX
**SD Elements:** [T438](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T438/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "A geração das leituras, os alarmes e os relatórios devem ser feitos em Python."
> (EN: Reading generation, alarms and reports must be done in Python.)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
Reports would be tested only for clinical content (vitals trends). Whether auditors can filter and summarize audit events on demand, and whether report generation leaves the audit trail untouched, would never be checked.

**Secure Implementation Pattern:**
```python
# backend/tests/test_audit_reports.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_audit_report_reduces_without_mutation(admin_token, snapshot_audit, seeded_demo_flow):
    before = snapshot_audit()                     # [(id, occurred_at, record_hash), ...]
    params = {"start": "2026-01-01T00:00:00Z", "end": "2100-01-01T00:00:00Z",
              "actions": ["alarm.acknowledge", "threshold.update"]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/reports/audit", params=params,
                        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["totals"]) <= {"alarm.acknowledge", "threshold.update"}
    assert body["totals"]["alarm.acknowledge"] >= 1
    after = snapshot_audit()
    assert after[: len(before)] == before          # nothing modified or reordered
    assert after[-1][0] > before[-1][0]            # report export itself was audited

@pytest.mark.asyncio
async def test_audit_report_forbidden_for_nurse(nurse_token):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/reports/audit", headers={"Authorization": f"Bearer {nurse_token}"})
    assert r.status_code == 403
```

**Implementation Guidance:**
- Seed a known demo flow (scenario, alarms, acknowledgements, threshold change, reset) and call the report endpoint from T437 with different filters (time window, actor, action, outcome).
- Assert summaries are correct (counts match seed) and on-demand (no pre-computed stale data).
- Snapshot `id`, `occurred_at`, `record_hash` before and after; assert identical prefix and order.
- Assert role restriction and that untrusted text in events is returned as plain data (no HTML rendering in the events screen; add a vitest for the React component).
- Reference: SD Elements guidance for T438.

**Success Criteria:**
- [ ] `backend/tests/test_audit_reports.py` passes.
- [ ] Test fails if the report endpoint is missing, mutates rows, or changes ordering.
- [ ] Frontend vitest confirms event text is rendered escaped.

**Status:** Pending
