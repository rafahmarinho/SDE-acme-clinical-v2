---
name: t1539-clear-browser-data-on-user-logout
description: Clear ACME Clinical browser data on logout by revoking the Supabase session server-side, returning Clear-Site-Data ("cache", "cookies", "storage") from the API and a frontend logout route, and wiping in-memory state, query caches and Realtime channels in the SPA.
---

# T1539: Clear browser data on user logout

**Category:** CODE_FIX
**SD Elements:** [T1539](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1539/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "devem aparecer nas telas e continuar salvos após recarregar a aplicação. Entregue o código"
> (EN: must appear on the screens and remain saved after reloading the application. Deliver the code)
> Source: specs/PRD.md, line 45

**What the spec implies (naive approach):**
"Remain saved after reloading" pushes developers to persist state in the browser (Supabase session in `localStorage`, cached patient lists, last-viewed patient). Workstations on a ward are shared; a logout that only calls `supabase.auth.signOut()` locally leaves PHI in storage and caches for the next user and keeps the refresh token valid server-side.

**Secure Implementation Pattern:**
```python
# backend/app/routers/auth.py
CLEAR_SITE_DATA = '"cache", "cookies", "storage"'

@router.post("/logout", status_code=204)
async def logged_out(request: Request, principal: CurrentPrincipal, body: LogoutIn | None = None) -> Response:
    async with transaction(principal) as conn:
        await execute(conn, "select public.revoke_session(%s, 'logout')", (_session_uuid(principal),))
    await record_event(principal, "auth.logout", "session", str(_session_uuid(principal)), outcome="success")
    return Response(status_code=204, headers={"Clear-Site-Data": CLEAR_SITE_DATA, "Cache-Control": "no-store"})
```
```ts
// frontend/src/auth/session.ts
export async function logout(): Promise<void> {
  try { await api.post("/auth/logout", { scope: "global" }); } catch { /* still clear locally */ }
  await supabase.auth.signOut({ scope: "global" });
  supabase.removeAllChannels();                  // stop Realtime vitals/alarms
  queryCache.clear();                            // in-memory PHI
  sessionStorage.clear(); try { localStorage.clear(); } catch {}
  window.location.replace("/logged-out");        // frontend/vercel.json sends Clear-Site-Data on this route
}
```

**Implementation Guidance:**
- Keep `POST /auth/logout` in `backend/app/routers/auth.py` revoking the server-side session (`revoke_session` in `supabase/migrations/0005_sessions.sql`) and returning `Clear-Site-Data`; note it only clears data for the API origin.
- Because the frontend is a different Vercel origin, add a static `/logged-out` route with a `Clear-Site-Data: "cache", "cookies", "storage"` header in `frontend/vercel.json` and navigate there after logout.
- In `frontend/src/auth/session.ts` / `AuthContext.tsx`, call `supabase.auth.signOut({ scope: "global" })`, remove Realtime channels (`frontend/src/hooks/useRealtime.ts`), reset React state/caches, clear session/local storage.
- Apply the same cleanup on idle timeout (`frontend/src/hooks/useIdleTimeout.ts`) and on forced revocation (401 `session_invalid`).
- Mark authenticated API responses `Cache-Control: no-store` so nothing PHI-bearing is left in the HTTP cache.
- Reference: SD Elements guidance for T1539.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_sessions.py`): `POST /auth/logout` returns 204 with `Clear-Site-Data` containing cache, cookies and storage, and the old token is rejected afterwards.
- [ ] `frontend/vercel.json` serves `/logged-out` with `Clear-Site-Data`.
- [ ] Vitest (`frontend/src/auth/session.test.ts`): after `logout()`, `sessionStorage`/`localStorage` contain no `sb-*` keys and no Realtime channels remain.

**Status:** Pending
