---
name: t26-expire-sessions-on-logout
description: Make logout in ACME Clinical truly end the Supabase Auth session on the server (refresh token revoked, API and RLS reject the old access JWT), stop background processes such as Realtime subscriptions, and clear local data on shared ward workstations.
---

# T26: Expire sessions on logout

**Category:** CODE_FIX
**SD Elements:** [T26](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T26/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

> "senha, arquivos e atualizações em tempo real."
> (EN: password, files and real-time updates.)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
A developer would implement logout as `supabase.auth.signOut()` followed by a redirect to the login screen. That clears the token in the current tab, but the access JWT already issued remains valid until it expires (default 1 hour) for the FastAPI API and for direct Supabase calls, Realtime channels may keep streaming patient vitals, and cached patient data stays in the browser of a shared ward workstation.

**Secure Implementation Pattern:**
```typescript
// frontend/src/services/auth.ts
export async function logout(reason: "user" | "idle" | "absolute" = "user") {
  try {
    // 1) Server-side: mark app session revoked, delete auth.sessions row; response carries Clear-Site-Data
    await api.post("/auth/logout", { reason });          // POST, never GET (T1542)
  } finally {
    await supabase.removeAllChannels();                  // stop Realtime vitals/alarm streams
    await supabase.auth.signOut({ scope: "local" });     // drop tokens from sessionStorage
    queryClient.clear();                                 // in-memory patient data
    sessionStorage.clear(); localStorage.removeItem("acme.ui-cache");
    window.location.replace(`/login?signedOut=${reason}`); // replace: Back button cannot return
  }
}
```
```sql
-- supabase/migrations/0001_schema.sql : make revocation effective for direct Supabase access too
create or replace function public.app_session_active() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from app_sessions s
                 where s.session_id = (auth.jwt() ->> 'session_id')::uuid
                   and s.revoked_at is null)
$$;
-- used in RLS, e.g.: create policy obs_read on observations for select
--   using (app_session_active() and has_ward_access(ward_id));
```

**Implementation Guidance:**
- `POST /auth/logout` in `backend/app/routers/auth.py`: set `app_sessions.revoked_at = now()` for the caller's `session_id` and delete the matching row from `auth.sessions` (removes the refresh token). Return `204` with `Clear-Site-Data: "cache", "cookies", "storage"` and `Cache-Control: no-store` (see T1540).
- `backend/app/core/security.py`: the auth dependency must look up `app_sessions` by the JWT `session_id` and reject revoked sessions with `401`, so a captured access token stops working immediately after logout, not at `exp`.
- Apply `app_session_active()` in RLS policies for tables and Storage buckets the SPA reads directly, and set a short access-token lifetime (for example 5-10 minutes) in Supabase Auth settings to bound Realtime exposure.
- Terminate associated processes: remove Realtime channels, stop polling timers and the idle-lock timer, and cancel in-flight requests (`AbortController`). Server-side simulation runs are global demo state and intentionally continue.
- Offer "Sign out of all devices" using `supabase.auth.signOut({ scope: "global" })` plus `POST /auth/logout?all=true`.
- If the previous session ended without explicit logout (idle/absolute timeout or browser closed), record `revoked_reason` and on the next login show a reminder: "Your last session was not signed out. Always sign out on shared workstations."
- Send `Cache-Control: no-store` on all authenticated API responses so the Back button cannot show cached patient data (verified by T93).
- Reference: SD Elements guidance for T26.

**Success Criteria:**
- [ ] After logout, the old access token gets `401` from every FastAPI endpoint and from RLS-protected Supabase tables.
- [ ] After logout, the old refresh token cannot obtain new tokens.
- [ ] No Realtime messages are received after logout (verified in the browser network tab).
- [ ] Next login after a timeout shows the "you did not sign out" reminder.
- [ ] Tests in `backend/tests/test_logout.py` (see T93).

**Status:** Applied
