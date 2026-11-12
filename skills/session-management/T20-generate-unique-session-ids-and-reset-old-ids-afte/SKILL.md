---
name: t20-generate-unique-session-ids-and-reset-old-ids-afte
description: Prevent session fixation in ACME Clinical by relying on Supabase Auth-issued random sessions only, registering a server-side session record after each login, and revoking and re-issuing sessions after password, role or MFA level changes.
---

# T20: Generate unique session IDs and reset old IDs after authentication

**Category:** CODE_FIX
**SD Elements:** [T20](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T20/)
**Priority:** 9/10 · **Phase:** requirements

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: services and database access. Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
With Supabase Auth, developers often assume sessions are "handled" and stop there: the API trusts any valid JWT, never tracks a session ID, accepts session identifiers passed in URLs, and keeps old sessions valid after a password reset or a role promotion (e.g. nurse to administrator), so a stolen or fixed token keeps its original or elevated reach.

**Secure Implementation Pattern:**
```python
# backend/app/routers/auth.py
@router.post("/session", response_model=SessionStart)
async def session_started(request: Request, principal: CurrentPrincipal) -> SessionStart:
    sid = _session_uuid(principal)               # Supabase `session_id` claim: server-generated, random
    async with transaction(principal) as conn:
        await execute(conn, "select public.register_session(%s, %s, %s)",
                      (sid, principal.user_id, _ip_hash(_ip_or_none(request))))
    return SessionStart(session_id=str(sid), idle_minutes=..., absolute_hours=...)

# backend/app/core/security.py - every request: the session must be registered and active
async def _enforce_session(request: Request, principal: Principal) -> None:
    verdict = await enforce_session(request, principal)   # unknown/revoked sid -> 401 session_invalid

# backend/app/routers/staff.py - privilege change invalidates existing sessions
async def apply_role_change(conn, user_id: UUID, new_role: Role):
    await execute(conn, "update public.staff_profiles set role = %s where id = %s", (new_role, user_id))
    await execute(conn, "select public.revoke_user_sessions(%s, 'role_changed')", (user_id,))
    await supabase_admin.sign_out(user_id, scope="global")   # refresh tokens revoked; new login = new sid
```

**Implementation Guidance:**
- Accept only Supabase-issued tokens (signature, `iss`, `aud`, `exp` verified in `decode_access_token`, `backend/app/core/security.py`); never accept session IDs from query strings or custom headers.
- After each successful login the frontend (`frontend/src/auth/AuthContext.tsx`) calls `POST /auth/session`; the API rejects tokens whose `session_id` is not registered/active (`session_state`, `register_session` in `supabase/migrations/0005_sessions.sql`).
- On password change/reset, role change (`backend/app/routers/staff.py` role-requests approve), MFA enrolment or account lock: call `revoke_user_sessions` and Supabase global sign-out; the user re-authenticates and gets a new session.
- On re-authentication (step-up), refresh the token so the new `amr`/`aal` claims are used; server-side state (preferences, unsent drafts) is reloaded by user ID, not copied from the old token.
- Reference: SD Elements guidance for T20.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_sessions.py`): a valid JWT whose `session_id` was never registered -> 401; after `revoke_user_sessions`, the old token -> 401.
- [ ] Pytest: approving a role change revokes all prior sessions of that user.
- [ ] Frontend test (`frontend/src/auth/session.test.ts`): login triggers session registration; tokens are never placed in URLs.

**Status:** Applied
