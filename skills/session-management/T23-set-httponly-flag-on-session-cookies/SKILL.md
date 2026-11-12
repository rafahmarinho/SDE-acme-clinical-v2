---
name: t23-set-httponly-flag-on-session-cookies
description: Ensure any session or refresh cookie used by ACME Clinical (for example an optional FastAPI-issued refresh cookie) is HttpOnly, and avoid Supabase SSR cookie storage for auth tokens because those cookies are JavaScript-readable by design.
---

# T23: Set HttpOnly flag on session cookies

**Category:** CODE_FIX
**SD Elements:** [T23](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T23/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
In the default architecture the React SPA holds the Supabase session (access JWT + refresh token) in Web Storage and sends it as `Authorization: Bearer`; no session cookie exists, so the HttpOnly flag cannot apply and the real XSS defence is CSP plus short-lived tokens. The risk appears when a developer "upgrades" to cookies: `@supabase/ssr` cookie storage writes `sb-<ref>-auth-token` cookies that the browser client must read, so they are deliberately *not* HttpOnly, and any XSS can steal the refresh token.

**Secure Implementation Pattern:**
```python
# backend/app/routers/auth.py  -- OPTIONAL backend-for-frontend refresh cookie
# Only if the team decides to keep the refresh token out of JavaScript.
from fastapi import Response

REFRESH_COOKIE = "__Host-acme_rt"

def set_refresh_cookie(resp: Response, refresh_token: str) -> None:
    resp.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,     # opaque Supabase refresh token, nothing else (T1092)
        httponly=True,           # not readable by document.cookie / XSS
        secure=True,             # T22
        samesite="strict",       # T557
        path="/",                # __Host- prefix requires Path=/ and no Domain (T404)
        # no max_age/expires: non-persistent, dies with the browser (T28)
    )

def clear_refresh_cookie(resp: Response) -> None:
    resp.delete_cookie(REFRESH_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
```

**Implementation Guidance:**
- Document the decision in the README: default = no auth cookies; Supabase session in `sessionStorage` (see T28), Bearer tokens to FastAPI.
- Do not configure `@supabase/ssr` / `createBrowserClient` cookie storage for auth tokens in `frontend/src/lib/supabase.ts`; it produces non-HttpOnly cookies containing the JWT and refresh token.
- If a cookie-based option is chosen, implement it in FastAPI (`backend/app/routers/auth.py`): `POST /auth/login` proxies the Supabase password grant, returns the access token in the JSON body (kept in memory only) and sets the refresh token with `httponly=True`; `POST /auth/refresh` reads the cookie and rotates it. Centralise cookie creation in one helper in `backend/app/core/security.py` so every `Set-Cookie` gets the flags.
- Because the SPA and API are deployed as separate Vercel projects, serve the API under the frontend origin (a `rewrites` entry in `frontend/vercel.json` mapping `/api/:path*` to the backend deployment) so the cookie is first-party; `*.vercel.app` is on the Public Suffix List, so cookies cannot be shared between two `vercel.app` subdomains.
- Keep a strict CSP (no inline scripts) regardless, because HttpOnly protects only the cookie, not the in-memory access token.
- Reference: SD Elements guidance for T23.

**Success Criteria:**
- [ ] No auth token is stored in a JavaScript-readable cookie (`document.cookie` shows no `sb-*-auth-token` or `acme_rt`).
- [ ] If the BFF option exists, every `Set-Cookie` for the session/refresh cookie contains `HttpOnly`.
- [ ] Unit test `backend/tests/test_cookies.py::test_refresh_cookie_flags` asserts the flag (see T91).

**Status:** Pending
