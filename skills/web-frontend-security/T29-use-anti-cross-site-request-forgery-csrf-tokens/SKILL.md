---
name: t29-use-anti-cross-site-request-forgery-csrf-tokens
description: Protect ACME Clinical state-changing API calls from CSRF by authenticating with a bearer token in the Authorization header (not ambient cookies), requiring JSON content types, checking Origin, and adding a double-submit CSRF token for any cookie-authenticated endpoint.
---

# T29: Use anti-Cross-Site Request Forgery (CSRF) tokens

**Category:** CODE_FIX
**SD Elements:** [T29](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T29/)
**Priority:** 7/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> "acompanhar manutenção. Reconhecer um alarme não encerra uma condição que ainda está"
> (EN: Allow linking a monitor to a bed, recording observations, acknowledging alarms and tracking maintenance. Acknowledging an alarm does not end a condition that is still occurring.)
> Source: specs/PRD.md, lines 33-35

**What the spec implies (naive approach):**
Acknowledging alarms, linking monitors to beds and resetting simulation data are state changes. If the API were authenticated with cookies (for example a session cookie set by the API) and accepted form-encoded posts, a malicious page opened on a ward PC could silently acknowledge alarms or unlink monitors, a patient-safety risk.

**Secure Implementation Pattern:**
```python
# backend/app/core/middleware.py
STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}

class CsrfGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method in STATE_CHANGING:
            origin = request.headers.get("origin")
            if origin and origin not in settings.cors_origins:
                return _error("Cross-site request rejected", 403)
            ctype = request.headers.get("content-type", "").split(";")[0]
            if not request.url.path.startswith("/files/") and ctype != "application/json":
                return _error("Unsupported content type", 415)         # blocks HTML form posts
            if request.cookies.get(SESSION_COOKIE):                    # only if a cookie-auth path exists
                header, cookie = request.headers.get("x-csrf-token"), request.cookies.get("csrf")
                if not header or not cookie or not hmac.compare_digest(header, cookie):
                    return _error("CSRF token missing or invalid", 403)
        return await call_next(request)
```
```ts
// frontend/src/services/api.ts - token header, no cookies
await fetch(`${API_BASE}/alarms/${id}/ack`, { method: "POST", credentials: "omit",
  headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ note }) });
```

**Implementation Guidance:**
- API authentication in `backend/app/core/security.py` reads only `Authorization: Bearer <supabase access token>`; tokens are never placed in cookies the browser sends automatically, which removes the CSRF vector (document in `docs/security/web-frontend.md`).
- Require `application/json` for JSON routes and `multipart/form-data` only on `/files/...` upload routes; reject `text/plain`/`application/x-www-form-urlencoded`.
- Validate `Origin` against the exact frontend origins (same list as CORS, T257) for state-changing methods.
- If any cookie is introduced (e.g. `set_secure_cookie` in `backend/app/routers/auth.py`), set `SameSite=Strict; Secure; HttpOnly` and add the double-submit token (random `secrets.token_urlsafe(32)`, compared with `hmac.compare_digest`).
- State changes never happen on `GET` (T1542).
- Reference: SD Elements guidance for T29.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_api_security.py`): `POST /alarms/{id}/ack` with `Content-Type: application/x-www-form-urlencoded` -> 415; with `Origin: https://evil.example` -> 403; without `Authorization` but with cookies -> 401.
- [ ] Any cookie set by the API has `SameSite=Strict`, `Secure`, `HttpOnly`.
- [ ] `frontend/src/services/api.test.ts` asserts requests use `credentials: "omit"` and the bearer header.

**Status:** Applied

**Decision:** no synchronizer/double-submit token. The API authenticates only with the Supabase access token in
the `Authorization` header (never cookies), which is a per-session unpredictable secret the browser does not
attach automatically, so it fulfils the anti-CSRF-token role. Layered with JSON-only bodies (415), an Origin
allow-list on state-changing requests (403) and strict CORS. Re-open if cookie authentication is ever added.
See `docs/security/web-frontend.md` ("Decision: CSRF defence").
