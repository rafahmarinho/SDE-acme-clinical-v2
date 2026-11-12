---
name: t3-require-old-passwords-when-users-change-passwords
description: Requires ACME Clinical staff to re-enter their current password (verified against Supabase Auth) before the profile screen lets them change it, and enables Supabase secure password change as defence in depth.
---

# T3: Require old passwords when users change passwords

**Category:** CODE_FIX
**SD Elements:** [T3](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T3/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A profile screen would offer "New password" and call `supabase.auth.updateUser({ password })` with the current session. Anyone holding an unattended workstation session or a stolen access token could then take over the account without knowing its password.

**Secure Implementation Pattern:**
```python
# backend/app/routers/profile.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, SecretStr

router = APIRouter(prefix="/me")

class PasswordChange(BaseModel):
    current_password: SecretStr
    new_password: SecretStr

@router.post("/password", status_code=204)
async def change_password(body: PasswordChange, claims: dict = Depends(verify_supabase_jwt)):
    email = claims["email"]
    # 1. Re-verify the old password against Supabase Auth (anon key, server side)
    ok = await supabase_password_grant(email, body.current_password.get_secret_value())
    if not ok:
        await uniform_delay()                                    # T73
        raise HTTPException(400, "Current password is incorrect.")
    new = body.new_password.get_secret_value()
    await assert_meets_minimum(new, context=[email.split("@")[0]])  # T5
    await assert_not_in_history(claims["sub"], new)                 # T4
    # 2. Apply with the service-role admin client (server-only key)
    await admin_client.auth.admin.update_user_by_id(claims["sub"], {"password": new})
    await audit("password_changed", claims["sub"])                  # T427 notification
```

**Implementation Guidance:**
- The Profile screen in `frontend/src/screens/` has three masked fields (current, new, confirm) and calls `POST /me/password`. It never calls `supabase.auth.updateUser({ password })` directly.
- `supabase_password_grant` posts to `{SUPABASE_URL}/auth/v1/token?grant_type=password` with the anon key and discards the returned session. Throttle this endpoint per user (T6) so it cannot become a brute-force oracle.
- Enable `secure_password_change = true` under `[auth.email]` in `supabase/config.toml`. GoTrue then requires reauthentication (an emailed nonce) for direct `updateUser` calls from older sessions, which covers clients that bypass the backend.
- Password recovery through the emailed reset link is the only flow that skips the old password, and it requires the one-time recovery session.
- After a successful change, sign out other sessions (`auth.admin.sign_out(..., scope="others")` or `supabase.auth.signOut({ scope: 'others' })`) and send a security notification.
- Reference: SD Elements guidance for T3.

**Success Criteria:**
- [ ] `POST /me/password` without `current_password`, or with a wrong one, fails and the password is unchanged.
- [ ] `backend/tests/test_change_password.py` (respx-mocked GoTrue) covers a wrong current password (400), a weak new password (422) and success (204 plus audit row).
- [ ] `secure_password_change = true` is present in `supabase/config.toml`.

**Status:** Applied
