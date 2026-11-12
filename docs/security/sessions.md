# Session management

Covers skills/session-management (T22-T28, T86-T95, T404, T405, T429, T430, T557, T1092, T1093, T1540).

## Design

| Piece | Where | Notes |
|-------|-------|-------|
| Session issuance | Supabase Auth | Access JWT (short-lived, carries a random `session_id`) and a rotating refresh token. A new `session_id` is issued on every sign-in, so a pre-login value can never be fixed (T86). |
| Token storage | `frontend/src/lib/supabase.ts` | `sessionStorage`, PKCE flow. A reload keeps the session; closing the tab or browser ends it. No `localStorage`, no cookies, no "remember me" option (T28/T95). |
| Transport | `frontend/src/services/api.ts` | `Authorization: Bearer` header only, `credentials: "omit"`. The API never reads tokens from the query string, so `?access_token=` gets 401 (T27/T94). |
| Registry | `public.app_sessions` (`supabase/migrations/0005_sessions.sql`) | Keyed by the verified JWT `session_id`, never by a session id the client sends. Writes go only through SECURITY DEFINER functions that `acme_api_rw` can execute. |
| Registration / heartbeat | `POST /v1/auth/session` (`backend/app/routers/auth.py`) | Called once per sign-in (and on reload) before any other API call, then as the activity heartbeat. It is idempotent: a revoked session cannot come back. |
| Logout | `POST /v1/auth/logout` + `frontend/src/auth/session.ts` | See below. |

## Controls

* **Concurrent sessions (T429/T430).** `register_session()` takes an advisory lock per user, so parallel logins are handled one at a time. It counts the user's live `auth.sessions` and keeps only the newest `max_concurrent_sessions` (security settings, default 2). For administrators the limit is capped at 1. Older sessions are revoked, oldest first: they are marked `concurrent_limit` and their `auth.sessions` row is deleted, which also kills the refresh token. The new session's sign-in notice says how many sessions were closed. On its next API call, a displaced browser gets 401 `session_revoked` and is told it was signed out because the account signed in on another device.
* **Idle timeout (T24/T90).** `session_idle_minutes` (security settings, 5-60, default 15).
  * Client: `useIdleTimeout`. Only `pointerdown`, `keydown`, `wheel` and `touchstart` count as activity; Realtime messages, polling and token refreshes do not. When the time runs out, the full logout runs. While the user is active, a heartbeat goes out at most once a minute.
  * Server: `last_activity_at` changes only on the heartbeat. `enforce_session()` refuses with 401 `session_idle` and revokes the session once the window has passed. This holds even if the client-side timer is bypassed.
* **Absolute timeout (T25/T92).** `session_absolute_hours` (default 12). The server measures it from `app_sessions.created_at`, so refreshing the JWT never extends it. Expired sessions get 401 `session_expired` and are revoked. `get_principal` also checks the token's first authentication time. The SPA gets `expires_at`, warns 10 minutes before the end and then signs out.
* **Logout (T26/T93/T1540).**
  1. `POST /v1/auth/logout` revokes the session and deletes its `auth.sessions` row (refresh token dead). With `{"scope":"global"}` it does this for every session of the user ("Sign out everywhere").
  2. The response carries `Clear-Site-Data: "cache", "cookies", "storage"` and `Cache-Control: no-store`.
  3. The SPA removes the Realtime channels, calls `signOut({scope:"local"})`, and clears sessionStorage, localStorage, IndexedDB, Cache Storage and any cookie scripts can see.
  4. It tells other tabs through `BroadcastChannel`, then leaves with `location.replace("/login")` so Back cannot show cached screens.
  5. Any 401 from the API runs the same clean-up.
* **Direct Supabase access.** Restrictive RLS policies call `app_session_active()` on the tables the browser reads through Realtime. A revoked, idle-expired or signed-out session therefore loses Realtime and PostgREST access as soon as it is revoked, not only when the JWT `exp` passes.
* **Session ids in URLs (T27/T94).** PKCE recovery links carry only a one-time `code`. supabase-js exchanges it and removes it from the address bar with `history.replaceState`. Downloads use short-lived signed URLs, never the user's JWT.
* **Cookies (T22/T23/T88/T91/T557/T404/T405/T1092/T1093).** The application sets **no cookies**: no auth cookie, no preference cookie, CORS `allow_credentials=False`. Tests check that no route returns `Set-Cookie` and that no cookie code with `domain=` exists. If a cookie is ever needed, it must be created with `set_secure_cookie()` in `backend/app/routers/auth.py`, which enforces:
  * `HttpOnly`, `Secure`, `SameSite=Strict`;
  * no `Domain` (host-only) and no `Max-Age`/`Expires` (ends with the browser);
  * a `__Host-` prefix (with `Path=/`) or a `__Secure-` prefix with a path inside `/v1/auth`;
  * no JWT as the value.

  Cookie values are never trusted for authorization.

## Platform settings (Supabase dashboard, record in the deployment checklist)

* Auth > Sessions:
  * set the access token (JWT) expiry to 10 minutes or less;
  * turn on refresh token rotation, with a reuse interval of 10 s or less;
  * set "Time-boxed user sessions" to 12 h and the inactivity timeout to 30 min, as backstops.
* Ward workstations: turn off the browser's "continue where you left off" / session restore by policy. Restoring a session would bring back `sessionStorage`.
* Each tab that signs in on its own counts as a session against the concurrent limit.

## Tests

* `backend/tests/test_sessions.py`: covers the session policy, idle and absolute timeouts with simulated time, the concurrent limit, registration keyed on `session_id`, the logout headers and replay, query-string tokens, cookies, and remember-me.
* `frontend/src/hooks/useIdleTimeout.test.ts`, `frontend/src/auth/session.test.ts` and `frontend/src/auth/supabaseClient.test.ts`.
