---
name: t404-avoid-setting-broad-paths-and-domains-on-session-c
description: Scope any ACME Clinical session or refresh cookie to the exact host (no Domain attribute, __Host- prefix) and the narrowest workable path, so sibling Vercel or company subdomains cannot read or overwrite it.
---

# T404: Avoid setting broad paths and domains on session cookies

**Category:** CODE_FIX
**SD Elements:** [T404](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T404/)
**Priority:** 4/10 · **Phase:** development

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
Because the web app and API are separate deployments, a developer adding a cookie (for example the optional FastAPI refresh cookie) would be tempted to set `Domain=.acme-clinical.example` and `Path=/` so both hosts see it. Every other subdomain (marketing site, preview deployments, a compromised test app) could then read or plant the session cookie (cookie tossing / fixation). The default Bearer-token design has no session cookie; this CM governs any cookie added later.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py - single place where session cookies are created
def set_refresh_cookie(resp: Response, token: str) -> None:
    # Option A (preferred): host-only cookie, Domain omitted, __Host- prefix
    resp.set_cookie("__Host-acme_rt", token, httponly=True, secure=True,
                    samesite="strict", path="/")          # __Host- requires Path=/ and no Domain

def set_refresh_cookie_narrow(resp: Response, token: str) -> None:
    # Option B: still host-only, but limited to the refresh endpoint path
    resp.set_cookie("__Secure-acme_rt", token, httponly=True, secure=True,
                    samesite="strict", path="/api/auth")   # sent only to /api/auth/refresh|logout
    # never: domain=".acme-clinical.example" or domain="vercel.app"
```

**Implementation Guidance:**
- Never pass `domain=` to `set_cookie` in `backend/app`; a host-only cookie is bound to the exact host that set it.
- Prefer Option A (`__Host-` prefix: browser enforces Secure, `Path=/`, no `Domain`). Choose Option B when the refresh token should reach only `/api/auth/*`, which limits exposure to other API routes; document the choice.
- Serve the API through the frontend origin via a `frontend/vercel.json` rewrite (see T557) so a host-only cookie works without widening the domain.
- Do not share cookies across Vercel preview deployments; previews use their own hosts and their own Supabase test project.
- Any non-session cookie (UI preferences) must also omit `Domain` and contain no sensitive data (T1092).
- Reference: SD Elements guidance for T404.

**Success Criteria:**
- [ ] No `Set-Cookie` header from ACME Clinical contains a `Domain` attribute.
- [ ] Session/refresh cookie uses `__Host-` (Path=/) or `__Secure-` with a path no broader than `/api/auth`.
- [ ] Verified by T405 tests.

**Status:** Pending
