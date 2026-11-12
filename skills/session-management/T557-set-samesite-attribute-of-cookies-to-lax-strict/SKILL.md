---
name: t557-set-samesite-attribute-of-cookies-to-lax-strict
description: Give every cookie used by ACME Clinical, especially any optional session/refresh cookie, SameSite=Strict, and keep the API same-site with the SPA so the cookie still works, as one layer of CSRF defence.
---

# T557: Set SameSite attribute of cookies to Lax/Strict

**Category:** CODE_FIX
**SD Elements:** [T557](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T557/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
With Bearer tokens in an `Authorization` header the browser never attaches credentials automatically, so classic CSRF does not apply to the default design. Once a cookie is introduced (the optional FastAPI refresh cookie, or a preference cookie), developers deploying two separate Vercel projects usually set `SameSite=None` "to make cross-origin requests work", which re-opens CSRF on `POST /auth/refresh`, alarm acknowledgement or simulation reset.

**Secure Implementation Pattern:**
frontend/vercel.json (makes the API same-origin with the SPA so SameSite=Strict works):
```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://acme-clinical-api.vercel.app/:path*" },
    { "source": "/((?!api/).*)", "destination": "/index.html" }
  ]
}
```
```python
# backend/app/core/security.py
response.set_cookie("__Host-acme_rt", refresh_token, httponly=True, secure=True,
                    samesite="strict", path="/")

# Defence in depth for cookie-authenticated endpoints (Note 2 of T557)
def require_same_origin(request: Request):
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin not in settings.allowed_origins:
        raise HTTPException(403, detail={"error": "bad_origin"})
```

**Implementation Guidance:**
- ACME Clinical is a private clinical application with no legitimate cross-site entry points that need a logged-in cookie, so use `SameSite=Strict` for every session/refresh cookie; `Lax` only for a non-sensitive preference cookie if a top-level link must see it.
- Never use `SameSite=None`. If the API stays on a separate `*.vercel.app` project, the two hosts are cross-site (the Public Suffix List treats each `vercel.app` subdomain as its own site), so a Strict cookie would not be sent; use the `frontend/vercel.json` rewrite above or custom domains under one registrable domain (for example `app.acme-clinical.example` and `api.acme-clinical.example`).
- Keep the other CSRF defences: state changes only via POST/PATCH/DELETE (T1542), `Origin` check (above) on cookie-authenticated routes, CORS `allow_origins` set to the exact frontend origin with `allow_credentials` only if the cookie option is used.
- Do not use `@supabase/ssr` cookie storage for the SPA; if it is ever used, configure its `cookieOptions` with `sameSite: "strict"` and `secure: true`.
- Reference: SD Elements guidance for T557.

**Success Criteria:**
- [ ] Every `Set-Cookie` from the API and frontend contains `SameSite=Strict` (or `Lax` with documented justification); none contains `SameSite=None`.
- [ ] A cross-site form POST to `/api/auth/refresh` or `/api/alarms/{id}/acknowledge` from another origin fails (no cookie sent, `403 bad_origin`).
- [ ] Test `backend/tests/test_cookies.py::test_samesite_strict` added.

**Status:** Pending
