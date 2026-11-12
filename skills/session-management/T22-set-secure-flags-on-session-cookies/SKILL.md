---
name: t22-set-secure-flags-on-session-cookies
description: Require the Secure attribute (and the __Host- prefix) on any session or refresh cookie used by ACME Clinical so it is only sent over HTTPS, and keep Supabase tokens off plain HTTP entirely.
---

# T22: Set secure flags on session cookies

**Category:** CODE_FIX
**SD Elements:** [T22](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T22/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
Vercel serves deployments over HTTPS, so a developer may assume cookie flags do not matter. If the optional FastAPI refresh cookie (see T23) is created without `Secure`, the browser will also send it over any plain-HTTP request to the same host (for example a custom domain before HSTS is in place, or a downgrade), exposing the session. Local development over `http://localhost` also tempts teams to disable the flag globally.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
from app.core.config import settings

def session_cookie_kwargs() -> dict:
    return dict(
        httponly=True,
        secure=True,          # always; browsers treat http://localhost as a secure context
        samesite="strict",
        path="/",
    )

# backend/app/main.py - reject accidental plain-HTTP use behind Vercel's proxy
@app.middleware("http")
async def require_https(request, call_next):
    if settings.env != "local" and request.headers.get("x-forwarded-proto", "https") != "https":
        return JSONResponse({"error": "https_required"}, status_code=400)
    resp = await call_next(request)
    resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return resp
```

**Implementation Guidance:**
- Default design: no session cookie (Supabase Bearer tokens). This CM then applies to any cookie the team adds later, chiefly the optional `__Host-acme_rt` refresh cookie.
- Build every session cookie through one helper (`session_cookie_kwargs()` in `backend/app/core/security.py`); never call `response.set_cookie` with ad-hoc arguments. Use the `__Host-` prefix: browsers refuse such cookies unless they carry `Secure`, `Path=/` and no `Domain`.
- Keep `secure=True` even locally; Chrome and Firefox accept Secure cookies on `http://localhost`. Do not add a config switch to turn it off in production.
- Add HSTS for the API and frontend (`frontend/vercel.json` `headers` block) so the browser never issues HTTP requests that could carry cookies.
- Ensure `SUPABASE_URL` and `VITE_API_BASE_URL` in the `.env.example` files are `https://` URLs.
- Reference: SD Elements guidance for T22.

**Success Criteria:**
- [ ] Every session/refresh `Set-Cookie` includes `Secure` and uses the `__Host-` prefix.
- [ ] No configuration flag can disable `Secure` in production.
- [ ] HSTS header present on frontend and API responses.
- [ ] Verified by `backend/tests/test_cookies.py` (see T88).

**Status:** Pending
