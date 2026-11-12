---
name: t1-use-multi-factor-authentication-for-remote-access
description: Requires Supabase TOTP multi-factor authentication (AAL2) for ACME Clinical administrator access (team management, settings, simulation reset), enforced in the React route guards, the FastAPI JWT checks and PostgreSQL RLS.
---

# T1: Use multi-factor authentication for remote access to high risk systems or administrative access to services

**Category:** CODE_FIX
**SD Elements:** [T1](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: Have nurse, physician, biomedical technician and administrator profiles.)
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
The administrator profile would sign in with email and password only, as every other role does. Its powers (create staff in "gestão da equipe", change alarm limits, reset the demo data) would then depend on a single knowledge factor, which phishing or password reuse can defeat.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
from fastapi import Depends, HTTPException, status

def require_admin_aal2(claims: dict = Depends(verify_supabase_jwt)) -> dict:   # see T10
    role = (claims.get("app_metadata") or {}).get("role")
    if role != "administrator":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    if claims.get("aal") != "aal2":       # password-only session = aal1
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA required",
                            headers={"WWW-Authenticate": 'Bearer error="insufficient_user_authentication"'})
    return claims
```
```typescript
// frontend/src/hooks/useRequireMfa.ts
const { data } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
if (isAdmin && data?.currentLevel !== 'aal2') {
  navigate(data?.nextLevel === 'aal2' ? '/mfa/verify' : '/mfa/enroll');
}
// enroll:  supabase.auth.mfa.enroll({ factorType: 'totp', friendlyName: 'ACME Clinical' })
// verify:  supabase.auth.mfa.challengeAndVerify({ factorId, code })
```
```sql
-- RLS defence in depth on admin-only tables
create policy admin_write_policy on public.password_policy as restrictive for all to authenticated
  using ((auth.jwt()->>'aal') = 'aal2');
```

**Implementation Guidance:**
- Enable TOTP MFA in `supabase/config.toml` (`[auth.mfa.totp] enroll_enabled = true`, `verify_enabled = true`) and in the hosted project.
- After an administrator logs in with a password, `frontend/src/hooks/useRequireMfa.ts` sends them to enrollment (QR code from `enroll()`) or verification. Admin screens stay hidden until the session reaches `aal2`.
- Protect every admin router in `backend/app/routers/` (team management, password policy, simulation reset) with `require_admin_aal2`. The UI check alone does not count.
- Add restrictive RLS policies that require `aal = 'aal2'` on admin-managed tables, so direct PostgREST calls with an aal1 token fail.
- Provide a recovery path: a second administrator removes a lost factor through the Admin API, and the action is audit-logged. Do not use security questions, which are the same factor as the password.
- Optionally offer MFA to physicians and nurses for remote access, as the role policy allows.
- Reference: SD Elements guidance for T1.

**Success Criteria:**
- [ ] An administrator session with `aal = aal1` gets 401 from every `/admin/*` endpoint and is redirected to MFA in the UI.
- [ ] `backend/tests/test_admin_mfa.py` signs JWTs locally with aal1 and aal2 claims and checks the 401 and 200 outcomes.
- [ ] RLS rejects writes to admin tables with an aal1 token (SQL test run with `set request.jwt.claims`).

**Status:** Applied
