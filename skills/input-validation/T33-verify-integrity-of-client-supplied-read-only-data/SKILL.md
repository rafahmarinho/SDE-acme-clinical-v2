---
name: t33-verify-integrity-of-client-supplied-read-only-data
description: Ensures ACME Clinical never trusts read-only values sent by the React client (patient/bed bindings, alarm state, user role, author ids, reading values) and derives them from server-side state instead.
---

# T33: Verify integrity of client-supplied read-only data

**Category:** CODE_FIX
**SD Elements:** [T33](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T33/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow linking a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
The frontend already displays the patient, bed, alarm severity and current user, so a developer may post them back verbatim (e.g. `{alarm_id, severity, acknowledged_by, patient_name}` or `{observation, author_id, role}`). An attacker can then acknowledge alarms as someone else, downgrade severities, or attach observations to another patient.

**Secure Implementation Pattern:**
```python
# backend/app/routers/alarms.py (pattern)
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import current_user, User
from app.schemas.common import StrictModel
from uuid import UUID

router = APIRouter()

class AckIn(StrictModel):          # client sends only the pointer + free text
    note: str | None = None

@router.post("/alarms/{alarm_id}/ack")
async def ack(alarm_id: UUID, body: AckIn, user: User = Depends(current_user), db=Depends(get_db)):
    alarm = await db.fetch_alarm(alarm_id)            # server state is the truth
    if alarm is None or not user.can_access_ward(alarm.ward_id):
        raise HTTPException(404)
    await db.ack_alarm(alarm_id, by=user.id, role=user.role, note=body.note)
    # severity, patient, condition_active stay as computed by services/alarms.py
    return {"id": alarm_id, "acknowledged": True, "condition_active": alarm.condition_active}
```

**Implementation Guidance:**
- Keep business logic on the server (`backend/app/services/alarms.py`, `simulation.py`): alarm severity, whether a condition is still active, reading values and thresholds are computed server-side.
- Clients send only identifiers (alarm id, monitor id, bed id) plus genuinely user-entered data; author, role, timestamps and derived fields come from the JWT (`backend/app/core/security.py`) and the database.
- Reject or ignore any extra read-only field via `extra="forbid"` Pydantic models.
- If a read-only value must round-trip through the client (e.g. a signed simulation snapshot or report parameters), protect it with an HMAC (`hmac.compare_digest`) keyed by a server secret from env vars.
- Enforce row ownership in Supabase RLS as a second layer (`supabase/migrations/0001_schema.sql`).
- Reference: SD Elements guidance for T33.

**Success Criteria:**
- [ ] No request model contains `author_id`, `acknowledged_by`, `role`, `severity` or computed reading fields.
- [ ] Test: posting an acknowledgement with a forged `acknowledged_by` returns 422 and the stored record shows the real user.
- [ ] Any HMAC-protected value that is modified client-side is rejected with 400.

**Status:** Applied
