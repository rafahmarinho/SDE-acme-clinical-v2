---
name: t27-turn-off-session-rewriting
description: Keep Supabase access/refresh tokens and recovery codes out of URLs in ACME Clinical: use the PKCE auth flow, strip auth parameters from the address bar, and make the FastAPI API accept tokens only from the Authorization header.
---

# T27: Turn off session rewriting

**Category:** CODE_FIX
**SD Elements:** [T27](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T27/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
There is no servlet-style `jsessionid` URL rewriting in FastAPI or React, but the equivalent risk exists. Supabase's default implicit flow returns `#access_token=...&refresh_token=...` in the URL of password-recovery links, and developers often add `?token=` query parameters to make file downloads, report exports or WebSocket connections work. Those tokens end up in browser history, Vercel request logs and `Referer` headers.

**Secure Implementation Pattern:**
```typescript
// frontend/src/lib/supabase.ts
export const supabase = createClient(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY, {
  auth: {
    flowType: "pkce",            // recovery link carries a one-time ?code=, not tokens
    detectSessionInUrl: true,    // exchanges the code once
    persistSession: true,
    storage: window.sessionStorage,
  },
});
// frontend/src/screens/ResetPassword.tsx: after the code exchange
window.history.replaceState(null, "", window.location.pathname);   // remove ?code= from the address bar
```
```python
# backend/app/core/security.py
bearer = HTTPBearer(auto_error=False)   # header only; no OAuth2 query-parameter fallback

async def verify_supabase_jwt(request: Request, cred=Depends(bearer)) -> Claims:
    if any(k in request.query_params for k in ("access_token", "token", "jwt", "refresh_token")):
        raise HTTPException(400, detail={"error": "token_in_url_not_allowed"})
    if cred is None:
        raise HTTPException(401, detail={"error": "missing_token"})
    return decode_and_validate(cred.credentials)
```

**Implementation Guidance:**
- Use `flowType: "pkce"` so password recovery and email confirmation links in Supabase redirect with a short-lived, single-use `code`, then strip it from the URL with `history.replaceState`.
- The FastAPI dependency in `backend/app/core/security.py` reads tokens only from `Authorization: Bearer`; never accept `?access_token=` (reject it explicitly so mistakes surface in tests).
- Downloads of reports and Storage files (`backend/app/services/reports.py`, Supabase Storage): fetch with the `Authorization` header and create a `Blob` URL, or issue short-lived Supabase Storage signed URLs (60-300 seconds) that are scoped to one object, never URLs embedding the user's JWT.
- Realtime: `supabase-js` puts only the public anon key in the WebSocket URL and sends the user JWT inside the channel join message; do not hand-roll WebSocket URLs with the user's token.
- Add `Referrer-Policy: strict-origin-when-cross-origin` (or `no-referrer`) in `frontend/vercel.json` and ensure `backend/app/core/logging.py` redacts `authorization` headers and any `code`/`token` query parameters.
- Reference: SD Elements guidance for T27.

**Success Criteria:**
- [ ] No access token, refresh token or session identifier appears in any URL, browser history entry or Vercel log during login, recovery, downloads or live monitoring.
- [ ] API returns `400` when a token is supplied in the query string.
- [ ] Recovery `code` is removed from the address bar after exchange and cannot be reused.
- [ ] Tests in `backend/tests/test_token_in_url.py` (see T94).

**Status:** Applied
