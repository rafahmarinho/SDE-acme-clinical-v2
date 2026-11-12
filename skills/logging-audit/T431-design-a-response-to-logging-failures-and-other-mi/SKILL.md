---
name: t431-design-a-response-to-logging-failures-and-other-mi
description: Defines how the ACME Clinical FastAPI backend reacts when audit/security logging fails (Supabase audit table unreachable, log sink errors) so that alarm generation and live monitoring keep working while responsible roles are alerted.
---

# T431: Design a response to logging failures and other minor failures

**Category:** CODE_FIX
**SD Elements:** [T431](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T431/)
**Priority:** 4/10 · **Phase:** architecture-design

**Spec Context:**
> "A geração das leituras, os alarmes e os relatórios devem ser feitos em Python."
> (EN: Reading generation, alarms and reports must be done in Python.)
> Source: specs/PRD.md, line 21

> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados."
> (EN: choose scenarios, advance the simulation, view events and reset the data.)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
A developer would call `supabase.table("audit_events").insert(...)` inline in every router and let any exception bubble up. A transient Supabase outage would then either crash alarm generation (a critical clinical function) or be silently swallowed, losing the audit trail with nobody notified.

**Secure Implementation Pattern:**
```python
# backend/app/core/logging.py
import collections, logging
from enum import Enum

security_log = logging.getLogger("acme.security")

class FailureAction(str, Enum):
    BUFFER_AND_RETRY = "buffer_and_retry"   # minor: audit DB unreachable
    BLOCK_ACTION = "block_action"           # critical: non-repudiable ack cannot be recorded

# Documented minor-failure catalogue (used by T432 tests)
FAILURE_POLICY = {
    "audit_insert_failed": FailureAction.BUFFER_AND_RETRY,
    "audit_buffer_full": FailureAction.BUFFER_AND_RETRY,   # drop oldest *buffered* only, alert
    "ack_audit_failed": FailureAction.BLOCK_ACTION,
}

_buffer: collections.deque = collections.deque(maxlen=500)

async def write_audit(db, event: dict, *, critical: bool = False) -> None:
    try:
        await db.insert_audit_event(event)
    except Exception:
        key = "ack_audit_failed" if critical else "audit_insert_failed"
        security_log.error("audit_failure", extra={"failure": key, "action": event.get("action")})
        await notify_admins(key)           # e.g. row in system_alerts table / Realtime channel
        if FAILURE_POLICY[key] is FailureAction.BLOCK_ACTION:
            raise                          # caller returns 503; ack is not accepted unaudited
        if len(_buffer) == _buffer.maxlen:
            security_log.critical("audit_buffer_full")
        _buffer.append(event)              # flushed by a retry on the next request / cron
```

**Implementation Guidance:**
- Create the failure catalogue in `backend/app/core/logging.py` listing each minor failure (audit insert error, log sink error, buffer full, Realtime publish error) and its action; commit it as the source list for T432 tests.
- Classify actions: alarm evaluation in `services/alarms.py` and reading generation in `services/simulation.py` must never be blocked by a logging failure; alarm acknowledgement in `routers/alarms.py` must be refused (HTTP 503, generic message) if its audit record cannot be written, because the acknowledgement requires non-repudiation (see T485).
- Alert the responsible role (administrator) by inserting into a `system_alerts` table and broadcasting on a Supabase Realtime channel only admins can subscribe to (RLS).
- Vercel functions are stateless: the in-memory buffer is best-effort only; add a retry flush at request start and document that Vercel runtime logs (stdout) are the fallback sink.
- Storage-full response: Supabase Postgres capacity alerts are platform settings; in-app, cap `details` JSON size so audit rows cannot exhaust storage.
- Reference: SD Elements guidance for T431.

**Success Criteria:**
- [ ] A documented `FAILURE_POLICY` list exists and every audit write goes through `write_audit`.
- [ ] Alarm generation continues when the audit insert raises (unit test with a failing fake DB).
- [ ] Alarm acknowledgement returns 503 and is not persisted when its audit write fails.
- [ ] An administrator alert row/Realtime event is produced on audit failure.

**Status:** Pending
