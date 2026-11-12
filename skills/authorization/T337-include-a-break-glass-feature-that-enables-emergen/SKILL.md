---
name: t337-include-a-break-glass-feature-that-enables-emergen
description: Provide an audited, time-limited break-glass flow letting an ACME Clinical nurse or physician view and respond to alarms for a patient outside their assigned ward in an emergency, with warning, justification, minimal scope and automatic expiry.
---

# T337: Include a 'break glass' feature that enables emergency functions

**Category:** CODE_FIX
**SD Elements:** [T337](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T337/)
**Priority:** 3/10 · **Phase:** requirements

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: "ward view, patient list and detail, live monitoring, alarms, devices,")
> Source: specs/PRD.md, line 25

> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow binding a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Once access is scoped by ward, a clinician covering a crashing patient in another ward would be blocked; teams then "fix" it by giving everyone access to all wards, or by sharing an administrator login. Both silently destroy least privilege and accountability.

**Secure Implementation Pattern:**
```python
# backend/app/routers/break_glass.py
class BreakGlassRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: UUID
    reason: constr(strip_whitespace=True, min_length=10, max_length=500)
    acknowledged_warning: Literal[True]

BREAK_GLASS_TTL = timedelta(minutes=30)
BREAK_GLASS_PERMS = frozenset({Perm.PATIENT_READ, Perm.ALARM_ACK, Perm.OBSERVATION_WRITE})  # no threshold changes

@router.post("/break-glass", status_code=201)
async def activate(body: BreakGlassRequest, request: Request,
                   user=Depends(require_recent_auth(Perm.PATIENT_READ)), db=Depends(get_db)):
    if user.role not in (Role.NURSE, Role.PHYSICIAN):
        raise HTTPException(403, "Not allowed")
    grant = await db.insert_break_glass(user_id=user.id, patient_id=body.patient_id,
                                        reason=body.reason, perms=sorted(BREAK_GLASS_PERMS),
                                        expires_at=utcnow() + BREAK_GLASS_TTL)
    await audit("break_glass.activated", actor=user, target=body.patient_id,
                detail={"reason": body.reason, "ip": request.client.host, "grant": str(grant.id)})
    await notify_ward_charge_and_admins(grant)     # supervisory review
    return grant
```
```sql
-- RLS: grant is honored only while unexpired and unrevoked
create policy patients_break_glass on clinical.patients for select to authenticated using (
  exists (select 1 from security.break_glass_grants g
          where g.user_id = auth.uid() and g.patient_id = id
            and g.revoked_at is null and g.expires_at > now()));
```

**Implementation Guidance:**
- Scope: emergency access to a single patient's live vitals, alarms and observations outside the user's ward. Not in scope: threshold changes, staff management, simulation reset, device management.
- UI (`frontend/src/components/BreakGlassDialog.tsx`): red warning that access is audited and the user takes full responsibility, mandatory reason (quick-pick + free text so it doesn't delay care), explicit "I accept" button.
- Grants are separate rows, not role changes; they expire automatically (30 min), can be ended early, and are re-checked on each request in `backend/app/core/security.py` and by RLS.
- Every action taken under a grant is audited with the grant ID; a review screen for administrators lists grants for post-event review.
- A scheduled job marks expired grants and closes Realtime subscriptions opened under them.
- Reference: SD Elements guidance for T337.

**Success Criteria:**
- [ ] Without a grant, cross-ward patient access returns 404; with a grant, only the listed permissions work.
- [ ] Grant expires after TTL and access is lost on the next request.
- [ ] Activation requires warning acknowledgement and reason; all details are audited and visible in the review screen.

**Status:** Applied
