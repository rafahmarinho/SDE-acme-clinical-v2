---
name: t429-limit-the-number-of-concurrent-sessions-for-each-a
description: Limit how many concurrent Supabase Auth sessions each ACME Clinical account may hold (stricter for administrators), terminate the oldest session when the limit is exceeded, and give users a panel to view and revoke their active sessions.
---

# T429: Limit the number of concurrent sessions for each account

**Category:** CODE_FIX
**SD Elements:** [T429](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T429/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: Have profiles for nurse, physician, biomedical technician and administrator.)
> Source: specs/PRD.md, line 39

> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A developer would call `supabase.auth.signInWithPassword()` from the SPA and let Supabase Auth issue a new session on every login. Supabase allows an unlimited number of parallel sessions per user by default, so an administrator account (which manages staff and thresholds) could stay logged in on many ward workstations at once, and a stolen session would never be displaced by the legitimate user's next login.

**Secure Implementation Pattern:**
```python
# backend/app/routers/auth.py  (called by the SPA right after a successful sign-in)
MAX_SESSIONS = {"administrator": 1, "biomedical_technician": 2, "physician": 2, "nurse": 2}

@router.post("/auth/session", response_model=SessionOut, status_code=201)
async def register_session(request: Request, claims: Claims = Depends(verify_supabase_jwt), db=Depends(get_db)):
    sid, uid, role = claims.session_id, claims.sub, claims.app_role
    limit = MAX_SESSIONS.get(role, 1)
    async with db.transaction():
        await db.execute("select pg_advisory_xact_lock(hashtext($1))", str(uid))  # serialise logins per user
        await db.execute(
            """insert into app_sessions (session_id, user_id, role, user_agent, ip_hash)
               values ($1, $2, $3, $4, $5) on conflict (session_id) do nothing""",
            sid, uid, role, request.headers.get("user-agent", "")[:256], hash_ip(request.client.host))
        # Keep the newest `limit` sessions, revoke the rest (oldest first)
        stale = await db.fetch(
            """select session_id from app_sessions
               where user_id = $1 and revoked_at is null
               order by created_at desc offset $2""", uid, limit)
        for row in stale:
            await revoke_session(db, row["session_id"], reason="concurrent_limit")  # marks app_sessions + deletes auth.sessions row
    return await get_session_out(db, sid)
```

**Implementation Guidance:**
- Define the limits per account type (requirement decision): administrators 1 session; nurse, physician and biomedical technician 2 (for example a ward workstation plus a central station). Store the limits in `backend/app/core/config.py` so they can be tuned without code changes.
- Add an `app_sessions` table in `supabase/migrations/0001_schema.sql` keyed by the Supabase JWT `session_id` claim (`session_id uuid primary key, user_id, role, created_at, last_activity_at, revoked_at, revoked_reason, user_agent, ip_hash`). Enable RLS so users can only `select` their own rows; only the backend (service connection) writes.
- After `signInWithPassword` succeeds, the SPA (`frontend/src/services/auth.ts`) calls `POST /auth/session`. The backend dependency in `backend/app/core/security.py` must reject any JWT whose `session_id` has no active `app_sessions` row, so skipping registration is not a bypass.
- When the limit is exceeded, terminate the previous session (recommended by SD Elements for privileged accounts): set `revoked_at`, and delete the row from `auth.sessions` (this invalidates the refresh token so it can no longer be renewed). Because Supabase access JWTs stay cryptographically valid until `exp`, keep the JWT expiry short in Supabase Auth settings and have RLS policies call a helper such as `app_session_active()` (see T26) for direct Supabase access (Storage, Realtime, PostgREST).
- As a platform-level backstop, Supabase Auth offers a "single session per user" setting (paid plans); it is all-or-nothing, so the per-role logic above is still needed for the 2-session roles.
- Optional panel (recommended): in the Profile screen (`frontend/src/screens/Profile*`) list `GET /auth/sessions` (created_at, last_activity_at, user agent, revoked reason) and allow `DELETE /auth/sessions/{session_id}` for the caller's own sessions; administrators may revoke staff sessions from team management (line 27 "gestão da equipe").
- Show the displaced session a clear message ("You were signed out because your account signed in on another device") when the API returns `401` with `error=session_revoked`.
- Reference: SD Elements guidance for T429.

**Success Criteria:**
- [ ] Logging in an administrator a second time revokes the first session: the first access token gets `401 session_revoked` from the API and its refresh token can no longer be used.
- [ ] A nurse can hold at most 2 active sessions; the third login revokes the oldest one.
- [ ] Concurrent logins for the same user are serialised (advisory lock) so the limit cannot be raced.
- [ ] Users can list and remotely terminate their own sessions from the Profile screen; history rows keep login time, user agent and idle time.
- [ ] Covered by tests in `backend/tests/test_concurrent_sessions.py` (see T430).

**Status:** Pending
