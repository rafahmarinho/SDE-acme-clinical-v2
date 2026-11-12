---
name: t14-enforce-the-principle-of-least-privilege
description: Give each ACME Clinical role (nurse, physician, biomedical technician, administrator), the FastAPI service and its database account only the privileges needed for their job, granted late and revoked promptly, scoped to the user's ward.
---

# T14: Enforce the principle of least privilege

**Category:** CODE_FIX
**SD Elements:** [T14](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T14/)
**Priority:** 9/10 · **Phase:** architecture-design

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, line 39

> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: "ward view, patient list and detail, live monitoring, alarms, devices,")
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
The simplest build gives every logged-in user access to every ward, patient and admin screen, and connects the backend to Supabase with the `service_role` key or the `postgres` superuser. A compromised nurse account or API bug would then expose all patients and allow resets or staff role changes.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py (continuation of the central matrix, see T15)
from datetime import datetime, timezone
from uuid import UUID

class CurrentUser(BaseModel):
    id: UUID
    role: Role
    ward_ids: frozenset[UUID]          # assignment, loaded per request (granted late)
    active: bool
    role_version: int                  # bumped on role change -> stale tokens rejected

async def get_current_user(token=Depends(bearer), db=Depends(get_db)) -> CurrentUser:
    claims = verify_supabase_jwt(token)                     # signature, exp, aud
    row = await db.fetchrow(
        "select id, role, active, role_version, ward_ids from api.staff_context($1)",
        claims["sub"])
    if row is None or not row["active"]:
        raise HTTPException(401, "Session no longer valid")  # revoked as soon as possible
    return CurrentUser(**row)

def assert_ward_access(user: CurrentUser, ward_id: UUID) -> None:
    if user.role in (Role.NURSE, Role.PHYSICIAN) and ward_id not in user.ward_ids:
        raise HTTPException(404, "Not found")              # don't reveal existence
```

**Implementation Guidance:**
- Define the role-permission matrix (see T15) with the minimum set per job: nurses read patients in assigned wards, record observations, acknowledge alarms; physicians additionally change alarm thresholds; biomedical technicians manage devices, maintenance and monitor-to-bed binding but do not read clinical notes; administrators manage staff and simulation but do not acknowledge alarms or change limits.
- Resolve permissions and ward assignments on every request in `backend/app/core/security.py` instead of embedding them in long-lived tokens; deactivating a staff member or changing their role takes effect on the next request.
- Connect the API with a dedicated non-owner role (`acme_api`, see T2617) rather than `postgres`/`service_role`; keep the service-role key out of `backend/` runtime except for the admin-only staff invitation call.
- Default new staff accounts (created in staff management) to no role/wards until an administrator assigns them.
- Reference: SD Elements guidance for T14.

**Success Criteria:**
- [ ] A nurse assigned to Ward A receives 404 for patients, alarms and live streams of Ward B (`backend/tests/test_least_privilege.py`).
- [ ] Deactivating a user or changing their role makes their next API call fail with 401/403 without waiting for token expiry.
- [ ] The backend's `DATABASE_URL` in `.env.example` references `acme_api`, not `postgres`.

**Status:** Pending
