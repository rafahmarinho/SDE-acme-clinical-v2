---
name: t340-use-an-account-and-identity-management-system
description: Builds ACME Clinical's team management on Supabase Auth as the identity system, with administrator-only lifecycle actions (invite, modify role, disable, reactivate, remove), role-based deny-by-default access, account usage monitoring and periodic review for human staff and service accounts.
---

# T340: Use an account and identity management system

**Category:** CODE_FIX
**SD Elements:** [T340](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T340/)
**Priority:** 7/10 · **Phase:** architecture-design

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe"
> (EN: limit settings, reports and team management)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
"Gestão da equipe" (team management) could be a simple CRUD on a `staff` table, with roles held in client-editable `user_metadata`, public sign-up left open, and no disable or review flow. Departed staff would keep access and users could raise their own role.

**Secure Implementation Pattern:**
```python
# backend/app/routers/admin.py
from fastapi import APIRouter, Depends
from supabase import AsyncClient

router = APIRouter(prefix="/admin/staff", dependencies=[Depends(require_admin_aal2)])

@router.post("", status_code=202)
async def invite(body: StaffCreate, actor=Depends(current_user), sb: AsyncClient = Depends(admin_client)):
    res = await sb.auth.admin.invite_user_by_email(body.email, {
        "redirect_to": f"{settings.frontend_url}/accept-invite"})
    await sb.auth.admin.update_user_by_id(res.user.id, {"app_metadata": {"role": body.role}})
    await db.insert_profile(res.user.id, body, created_by=actor.id)
    await audit("staff.invited", actor.id, target=res.user.id)
    return {"detail": "Invitation processed"}

@router.post("/{uid}/disable", status_code=204)
async def disable(uid: str, actor=Depends(current_user), sb: AsyncClient = Depends(admin_client)):
    await sb.auth.admin.update_user_by_id(uid, {"ban_duration": "876000h"})  # hard lock
    await sb.auth.admin.sign_out(uid)                                       # revoke sessions
    await db.execute("update profiles set is_active=false where id=$1", uid)
    await audit("staff.disabled", actor.id, target=uid)
```
```sql
-- roles from app_metadata (server-set only); deny by default
alter table public.patients enable row level security;   -- no policy = no access
create policy clinical_read on public.patients for select to authenticated
  using ((auth.jwt()->'app_metadata'->>'role') in ('nurse','physician','administrator'));
```

**Implementation Guidance:**
- Disable public sign-up (`[auth] enable_signup = false` in `supabase/config.toml` and the hosted project). Accounts are created only through `POST /admin/staff`.
- Keep roles in `app_metadata` (only the service role can write it) and mirror them in `profiles.role`. Never authorize from `user_metadata`. Optionally add a custom access token hook to put the role claim in the JWT.
- Provide invite, change role, disable (ban plus sign-out), reactivate and delete in the Team Management screen. Each requires an MFA administrator, records the account manager (`created_by`) and is audit-logged.
- Service accounts: the backend service role key and the cron secret are inventoried non-human accounts (T10), documented in the README with an owner and rotation procedure.
- Monitoring and review: expose `last_sign_in_at` and an inactive-account report (for example 90 days without sign-in) for periodic review. Re-verify identity (current password or MFA) before changing authentication factors (T3).
- Deny by default: RLS enabled on every table, FastAPI routes require a verified JWT unless explicitly public, and new users get no role until an administrator assigns one.
- Remove default installation accounts after setup (T61).
- Reference: SD Elements guidance for T340.

**Success Criteria:**
- [ ] Public sign-up is disabled, and only aal2 administrators can create, modify, disable or remove accounts.
- [ ] A disabled user's existing session fails on the next API call, and a new login is refused.
- [ ] `backend/tests/test_staff_lifecycle.py` covers invite, role change, disable and reactivate, and checks that users cannot set their own role through `updateUser({ data })`.

**Status:** Applied
