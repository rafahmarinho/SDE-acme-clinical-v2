---
name: t15-centralize-authorization
description: Route every ACME Clinical API authorization decision (nurse, physician, biomedical technician, administrator) through one central FastAPI dependency and permission matrix in backend/app/core/security.py, backed by Supabase RLS, instead of ad-hoc checks in routers or the React UI.
---

# T15: Centralize authorization

**Category:** CODE_FIX
**SD Elements:** [T15](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T15/)
**Priority:** 9/10 · **Phase:** architecture-design

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, line 39

> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: "...filters, loading states and error messages. Adapt the navigation to the user profiles")
> Source: specs/PRD.md, line 13

**What the spec implies (naive approach):**
A developer would likely hide menu items per role in React and sprinkle `if user.role == "admin"` checks across individual routers (or none at all). Role logic then diverges between screens and endpoints, and any API call made directly (curl, proxy) bypasses the hidden navigation.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
from enum import StrEnum
from fastapi import Depends, HTTPException, status

class Role(StrEnum):
    NURSE = "nurse"; PHYSICIAN = "physician"
    BIOMED = "biomedical_technician"; ADMIN = "administrator"

class Perm(StrEnum):
    PATIENT_READ = "patient:read"; OBSERVATION_WRITE = "observation:write"
    ALARM_ACK = "alarm:ack"; THRESHOLD_WRITE = "threshold:write"
    DEVICE_MANAGE = "device:manage"; MONITOR_BIND = "monitor:bind"
    MAINTENANCE_WRITE = "maintenance:write"; STAFF_MANAGE = "staff:manage"
    SIM_CONTROL = "simulation:control"; SIM_RESET = "simulation:reset"
    REPORT_READ = "report:read"; AUDIT_READ = "audit:read"

# Single source of truth; anything not listed is denied.
PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.NURSE: frozenset({Perm.PATIENT_READ, Perm.OBSERVATION_WRITE, Perm.ALARM_ACK, Perm.REPORT_READ}),
    Role.PHYSICIAN: frozenset({Perm.PATIENT_READ, Perm.OBSERVATION_WRITE, Perm.ALARM_ACK,
                               Perm.THRESHOLD_WRITE, Perm.REPORT_READ}),
    Role.BIOMED: frozenset({Perm.DEVICE_MANAGE, Perm.MONITOR_BIND, Perm.MAINTENANCE_WRITE}),
    Role.ADMIN: frozenset({Perm.STAFF_MANAGE, Perm.SIM_CONTROL, Perm.SIM_RESET, Perm.AUDIT_READ, Perm.REPORT_READ}),
}

def require(perm: Perm):
    async def checker(user: "CurrentUser" = Depends(get_current_user)) -> "CurrentUser":
        if perm not in PERMISSIONS.get(user.role, frozenset()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
        return user
    return checker

# routers/alarms.py
# @router.post("/alarms/{alarm_id}/ack")
# async def ack(alarm_id: UUID, user = Depends(require(Perm.ALARM_ACK))): ...
```

**Implementation Guidance:**
- Put the role enum, permission enum, role-to-permission matrix and `require()` dependency only in `backend/app/core/security.py`; routers in `backend/app/routers/*.py` must import from there and never compare role strings themselves.
- Load the role from a server-trusted source (the `staff` table or a Supabase `app_metadata` claim set only by the backend/admin), never from `user_metadata` or a request header.
- Object-level checks (ward membership, monitor ownership) live in the same module as helpers such as `assert_patient_access(user, patient_id)`, called by services.
- Mirror the same matrix in Supabase RLS policies (`supabase/migrations/`) using a `public.has_permission(perm text)` SQL function so direct Supabase client/Realtime access is consistent.
- Expose the user's effective permissions via `GET /me`; the frontend (`frontend/src/lib/permissions.ts`) uses it only to adapt navigation — it is UX, not enforcement.
- Reference: SD Elements guidance for T15.

**Success Criteria:**
- [ ] `grep -r "role ==" backend/app/routers` returns nothing; all routers use `Depends(require(...))`.
- [ ] `backend/tests/test_authz_matrix.py` parametrizes every role x every protected endpoint and asserts 403 for permissions absent from `PERMISSIONS`.
- [ ] RLS helper `has_permission()` and the Python matrix are generated from / checked against the same definition (test compares them).

**Status:** Applied
