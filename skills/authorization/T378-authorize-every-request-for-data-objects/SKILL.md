---
name: t378-authorize-every-request-for-data-objects
description: Authorize each ACME Clinical request against the specific object (patient, alarm, monitor, observation, attachment, staff record) using the session principal's ward assignments and ownership, returning 404 for objects outside scope, enforced in FastAPI and Supabase RLS.
---

# T378: Authorize every request for data objects

**Category:** CODE_FIX
**SD Elements:** [T378](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T378/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow linking a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Routes like `GET /patients/{patient_id}`, `POST /alarms/{alarm_id}/ack`, `PATCH /monitors/{id}/bed` and `GET /files/{attachment_id}/url` check only the role, then load the object by the ID in the URL. A nurse on Ward A can read Ward B patients, acknowledge their alarms, or move another ward's monitor simply by changing the UUID (IDOR / BOLA).

**Secure Implementation Pattern:**
```python
# backend/app/routers/alarms.py
@router.post("/{alarm_id}/ack", response_model=AlarmOut)
async def acknowledge(alarm_id: UUID, body: AckIn,
                      principal: Principal = Depends(require(Perm.alarms_ack))):
    async with transaction(principal) as conn:          # sets request.jwt claims -> RLS applies
        row = await fetch_one(conn,
            """select a.id from public.alarms a
               where a.id = %s and public.can_access_patient(a.patient_id)""",   # object-level check
            (alarm_id,))
        ensure_visible(row, "Alarm")                     # 404, do not reveal existence
        return await alarms.acknowledge(conn, alarm_id, principal.user_id, body.note)  # actor from session
```
```sql
-- supabase/migrations/0003_authz_rbac.sql
create policy alarms_ack on public.alarms for update to acme_api_rw
  using (public.can_access_patient(patient_id) and public.has_permission('alarms:ack'))
  with check (acknowledged_by = public.current_staff_id());
```

**Implementation Guidance:**
- For every route taking an object ID in `backend/app/routers/*.py`, scope the query by the principal (ward assignments via `can_access_ward`/`can_access_patient`, ownership via `current_staff_id()`), and call `ensure_visible`/`not_found` from `backend/app/core/security.py` (404 for both "missing" and "not yours").
- Take actor IDs (`acknowledged_by`, `recorded_by`, `uploaded_by`) from `principal.user_id`, never from the body; `/profile` endpoints use the session user, not a path ID.
- Check field-level authorization on updates: e.g. biomedical technicians may change a monitor's bed link and maintenance, not patient data; reject extra fields with `Strict` models.
- Run queries inside `transaction(principal)` (`backend/app/db.py`) so RLS in `supabase/migrations/0002_roles_rls.sql`/`0003_authz_rbac.sql` is a second layer; Realtime subscriptions and Storage objects use the same RLS functions.
- Break-glass access (`backend/app/routers/break_glass.py`) must be time-bound, justified and audited.
- Reference: SD Elements guidance for T378.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_authorization.py`): nurse assigned to Ward A gets 404 for `GET /patients/{wardB_patient}`, `POST /alarms/{wardB_alarm}/ack`, `GET /files/{wardB_attachment}/url`.
- [ ] Pytest (`backend/tests/test_database_policies.py`): RLS denies the same accesses when queried directly as `acme_api_rw` with the nurse's claims.
- [ ] Supplying `acknowledged_by`/`user_id` in a body is rejected (422) or ignored.

**Status:** Applied
