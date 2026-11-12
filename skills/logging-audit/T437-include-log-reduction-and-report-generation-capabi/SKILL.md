---
name: t437-include-log-reduction-and-report-generation-capabi
description: Adds Python-based audit log reduction and report generation to ACME Clinical (filters, summaries, anomaly hints) that never modifies source records or their ordering and renders untrusted event text safely in the events screen.
---

# T437: Include log reduction and report generation capabilities

**Category:** CODE_FIX
**SD Elements:** [T437](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T437/)
**Priority:** 4/10 · **Phase:** architecture-design

**Spec Context:**
> "A geração das leituras, os alarmes e os relatórios devem ser feitos em Python."
> (EN: Reading generation, alarms and reports must be done in Python.)
> Source: specs/PRD.md, line 21

> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados."
> (EN: choose scenarios, advance the simulation, view events and reset the data.)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
An events screen that dumps the whole table, and reports focused only on vitals. Investigators would have no way to summarize who acknowledged which alarms, spot unusual activity, or filter by actor/action — and raw event text could be rendered as HTML.

**Secure Implementation Pattern:**
```python
# backend/app/services/reports.py
from collections import Counter
from datetime import datetime
from pydantic import BaseModel, Field

class AuditQuery(BaseModel):
    start: datetime; end: datetime
    actions: list[str] = Field(default_factory=list, max_length=20)
    actor_id: str | None = None
    limit: int = Field(1000, le=10_000)

async def audit_summary(db, q: AuditQuery) -> dict:
    rows = await db.select_audit(q)              # read-only, parameterized, ORDER BY id
    by_action = Counter(r["action"] for r in rows)
    by_actor = Counter(r["actor_id"] for r in rows)
    failures = Counter(r["actor_id"] for r in rows if r["outcome"] == "failure")
    anomalies = [a for a, n in failures.items() if n >= 5]          # e.g. repeated denials
    unacked = [r for r in rows if r["action"] == "alarm.raised"
               and not any(x["action"] == "alarm.acknowledge" and x["target_id"] == r["target_id"] for x in rows)]
    return {"window": [q.start, q.end], "totals": dict(by_action), "by_actor": dict(by_actor),
            "suspicious_actors": anomalies, "unacknowledged_alarms": len(unacked),
            "first_id": rows[0]["id"] if rows else None, "last_id": rows[-1]["id"] if rows else None}
```

**Implementation Guidance:**
- Implement reduction in `backend/app/services/reports.py` (Python, per PRD) and expose `GET /reports/audit` in `routers/reports.py`, restricted to administrator (and physician if policy allows); the call itself is audited (T45 "data export").
- Reduction is read-only: SELECT with filters (time window, action, actor, target, outcome), ordered by `id`/`occurred_at`; never update source rows or reorder; include first/last IDs and chain verification result (T485) in the report.
- Let administrators configure which auditable event categories are captured per component via a `audit_settings` table (changes to it are themselves audited).
- Events screen in `frontend/src/screens`: render all fields as text (React escaping; no `dangerouslySetInnerHTML`); CSV export must neutralize formula injection (prefix `=,+,-,@` with `'`).
- Reference: SD Elements guidance for T437.

**Success Criteria:**
- [ ] `/reports/audit` returns summaries by action/actor/outcome and anomaly hints.
- [ ] Source `audit_events` row count, hashes and order are unchanged after report generation (test).
- [ ] Events containing `<script>` or `=cmd|` render/export inertly.

**Status:** Applied
