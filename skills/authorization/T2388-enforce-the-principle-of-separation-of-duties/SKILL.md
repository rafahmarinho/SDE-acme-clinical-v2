---
name: t2388-enforce-the-principle-of-separation-of-duties
description: Define non-overlapping ACME Clinical duties so no single user can both perform and conceal a sensitive action, e.g. no self role changes, two-administrator approval for privilege grants, append-only audit and administrators kept out of clinical actions.
---

# T2388: Enforce the principle of separation of duties

**Category:** CODE_FIX
**SD Elements:** [T2388](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T2388/)
**Priority:** 9/10 · **Phase:** architecture-design

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you can create something very visual in 3D if")
> Source: specs/PRD.md, line 27

> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
An "administrator" profile usually becomes a superuser: it can change anyone's role (including its own), edit alarm limits, acknowledge alarms, reset data and delete events. One account could then raise its privileges, silence a patient's alarm and erase the trace.

**Secure Implementation Pattern:**
```python
# backend/app/services/staff.py
SENSITIVE_ROLES = {Role.ADMIN, Role.PHYSICIAN}

async def request_role_change(actor: CurrentUser, target_id: UUID, new_role: Role, db):
    if target_id == actor.id:
        raise HTTPException(403, "You cannot change your own role")
    if new_role in SENSITIVE_ROLES:
        # authorization and verification split: a second administrator must approve
        return await db.insert_role_change_request(actor.id, target_id, new_role)
    return await apply_role_change(actor.id, target_id, new_role, approver=None, db=db)

async def approve_role_change(approver: CurrentUser, request_id: UUID, db):
    req = await db.get_role_change_request(request_id, for_update=True)
    if req.requested_by == approver.id or req.target_id == approver.id:
        raise HTTPException(403, "Requester or target cannot approve")
    await apply_role_change(req.requested_by, req.target_id, req.new_role, approver.id, db)
```
```sql
-- supabase/migrations/0003_audit.sql : recording is separate from administration
revoke update, delete, truncate on audit.events from acme_api, authenticated;
grant insert on audit.events to acme_api;      -- append-only
grant select on audit.events to acme_auditor;  -- review by a distinct role
```

**Implementation Guidance:**
- Document the conflicting areas in `docs`/README: authorization (staff role grants), custody (device/monitor binding), recording (observations, alarm acknowledgements, audit) and verification (audit review).
- Static SoD: administrators do not hold `alarm:ack`, `threshold:write` or `observation:write`; biomedical technicians bind monitors but cannot acknowledge alarms or change limits (matrix in `backend/app/core/security.py`).
- Dynamic SoD in `backend/app/services/staff.py`: no self role changes; grants of administrator/physician need a second administrator; requester cannot approve.
- Threshold changes by a physician are recorded with before/after values; the physician cannot delete that record.
- Audit table is append-only for the API role; nobody using the app can update/delete it.
- Reference: SD Elements guidance for T2388.

**Success Criteria:**
- [ ] An administrator cannot change their own role or approve their own request (tests in `backend/tests/test_separation_of_duties.py`).
- [ ] Administrator token gets 403 on `POST /alarms/{id}/ack` and `PUT /thresholds/{id}`.
- [ ] `UPDATE`/`DELETE` on `audit.events` as `acme_api` fails.

**Status:** Pending
