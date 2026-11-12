---
name: t338-control-access-to-resources-through-user-authentic
description: Control access to every ACME Clinical resource (patients, readings, alarms, monitors, thresholds, reports, staff, simulation, files) through Supabase authentication plus server-side RBAC for the four roles, deny-by-default, step-up re-authentication for critical actions, unique device identity and always-available logout.
---

# T338: Control access to resources through user authentication and authorization

**Category:** CODE_FIX
**SD Elements:** [T338](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T338/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: loss of connection. Have nurse, physician, biomedical technician and administrator profiles.)
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
Four roles are named but not their permissions, so a naive build gives every logged-in user full access, or uses ad-hoc `if role == "admin"` checks scattered across routes. Admin functions (staff management, security settings, data reset) are reachable by anyone authenticated, simulated monitors post data without any identity, and critical changes need no re-authentication.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
class Role(StrEnum):
    nurse = "nurse"; physician = "physician"; biomed = "biomedical_technician"; admin = "administrator"

class Perm(StrEnum):
    patients_read = "patients:read"; observations_write = "observations:write"
    alarms_ack = "alarms:ack"; thresholds_manage = "thresholds:manage"
    devices_manage = "devices:manage"; maintenance_write = "maintenance:write"
    reports_read = "reports:read"; staff_manage = "staff:manage"
    settings_manage = "settings:manage"; simulation_control = "simulation:control"

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {        # deny by default: absent = forbidden
    Role.nurse: frozenset({Perm.patients_read, Perm.observations_write, Perm.alarms_ack}),
    Role.physician: frozenset({Perm.patients_read, Perm.observations_write, Perm.alarms_ack,
                               Perm.thresholds_manage, Perm.reports_read}),
    Role.biomed: frozenset({Perm.devices_manage, Perm.maintenance_write}),
    Role.admin: frozenset({Perm.staff_manage, Perm.settings_manage, Perm.reports_read,
                           Perm.simulation_control}),
}

# critical, PHI-wide or admin changes require a fresh authentication (aal2 / recent login)
@router.post("/{user_id}/role-requests", dependencies=[Depends(require_recent_auth(Perm.staff_manage))])
```

**Implementation Guidance:**
- Keep one permission table (`ROLE_PERMISSIONS`) in `backend/app/core/security.py` and document it in `docs/security/authorization.md`; mirror it in SQL `has_permission()` (`supabase/migrations/0003_authz_rbac.sql`) for RLS.
- Authenticate every request with the Supabase JWT (`get_principal`), verify signature, `aud`, `exp`, and load the active staff profile; inactive/locked staff get 401/403.
- Use `require_recent_auth` (step-up, `STEP_UP_MAX_AGE`) for staff/role changes, security settings, data reset, bulk export and erasure; frontend prompts via `frontend/src/components/StepUpDialog.tsx` / `frontend/src/lib/reauth.ts`; consider requiring MFA (aal2) for administrators.
- Role changes go through a request/approval flow (`backend/app/routers/staff.py` role-requests) and force session re-issue (T20).
- Simulated monitors authenticate individually with per-device secrets (`backend/app/services/device_auth.py`, T558).
- Logout is reachable from every authenticated screen (header in `frontend/src/App.tsx`).
- Reference: SD Elements guidance for T338.

**Success Criteria:**
- [ ] `backend/tests/test_authorization.py` asserts the full role x route matrix and that a role absent from the table gets nothing.
- [ ] Pytest: admin with a login older than `STEP_UP_MAX_AGE` gets 401 `step_up_required` on `PATCH /settings/security` and `POST /simulation/reset`.
- [ ] Frontend test: a logout control is present on all authenticated layouts.

**Status:** Applied
