---
name: t517-protect-user-registration-and-account-modification
description: Protects ACME Clinical's account creation (administrator staff invites) and email change flows against user enumeration with uniform responses, anti-automation, owner warnings, admin alerts and single-use expiring Supabase confirmation links.
---

# T517: Protect user registration and account modification pages against user enumeration

**Category:** CODE_FIX
**SD Elements:** [T517](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T517/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Staff are created in team management and can edit their email on the profile screen. A naive build would show "Email already registered" in both places, and leaving Supabase public sign-up enabled would expose `/auth/v1/signup` to anyone as an enumeration oracle.

**Secure Implementation Pattern:**
```python
# backend/app/routers/admin.py - uniform staff invite
UNIFORM = {"detail": "Invitation processed. If the address can receive invitations, an email has been sent."}

@router.post("/admin/staff", status_code=202, dependencies=[Depends(require_admin_aal2)])
async def invite(body: StaffCreate, actor=Depends(current_user)):
    async with uniform_auth_timing():                          # T73
        existing = await db.fetchrow("select id from profiles where email=$1", body.email)
        if existing:
            await notify_user(existing["id"], "account_creation_attempt")   # warn owner
            await alert_admins("duplicate_staff_invite", actor.id, body.email)
        else:
            await create_and_invite(body, actor)               # single-use link, expires (otp_expiry)
    return UNIFORM
```
```typescript
// frontend/src/services/profile.ts - email change
export async function changeEmail(newEmail: string) {
  await supabase.auth.updateUser({ email: canonicalEmail(newEmail) }).catch(() => undefined);
  return 'If this address can be used, a confirmation link has been sent to it.';
}
```

**Implementation Guidance:**
- Turn off public registration (`[auth] enable_signup = false`). ACME Clinical has no self-service sign-up, which removes the main oracle. The invite endpoint is reachable only by MFA administrators (T1) and is rate-limited.
- Email change: enable `double_confirm_changes = true` under `[auth.email]` so both old and new addresses must confirm. Show the same message whether or not the new address is taken. Map Supabase errors such as `email_exists` to that message.
- When an existing address is targeted, send a warning to the owner and an abnormal-behavior alert to administrators (in-app notification plus simulated email service, since the PRD wants external integrations simulated).
- Links: Supabase invite and email-change links are one-time OTP links. Set `otp_expiry` to 3600 seconds or less.
- Anti-automation: CAPTCHA is enabled for Auth endpoints. `[auth.rate_limit] email_sent` caps the volume.
- Reference: SD Elements guidance for T517.

**Success Criteria:**
- [ ] Invite and email-change responses are byte-identical for existing and new emails.
- [ ] Duplicate attempts generate an owner warning and an admin alert (`backend/tests/test_invite_enumeration.py`).
- [ ] `enable_signup = false`, `double_confirm_changes = true` and `otp_expiry <= 3600` are set in `supabase/config.toml`.

**Status:** Applied
