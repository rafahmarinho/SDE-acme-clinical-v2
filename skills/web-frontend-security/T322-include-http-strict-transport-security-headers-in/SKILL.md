---
name: t322-include-http-strict-transport-security-headers-in
description: Sends a Strict-Transport-Security header from both ACME Clinical Vercel deployments (SPA via vercel.json, FastAPI via middleware) so browsers only reach the clinical web app and API over HTTPS.
---

# T322: Include HTTP Strict-Transport-Security headers in HTTPS responses

**Category:** CODE_FIX
**SD Elements:** [T322](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T322/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "README com os passos para rodar e publicar a versão web e a API na Vercel."
> (EN: README with the steps to run and publish the web version and the API on Vercel.)
> Source: specs/PRD.md, line 49

**What the spec implies (naive approach):**
Vercel serves HTTPS and redirects HTTP, but a developer may assume that is enough. On custom domains, or if HSTS is not explicit on the API, a user on hospital Wi-Fi typing the bare domain can be downgraded/MITM'd on the first request, exposing Supabase tokens and patient data.

**Secure Implementation Pattern:**
```json
{
  "headers": [{
    "source": "/(.*)",
    "headers": [{ "key": "Strict-Transport-Security", "value": "max-age=63072000; includeSubDomains" }]
  }]
}
```
```python
# backend/app/core/security.py (SecurityHeadersMiddleware)
from app.core.config import settings

HSTS = "max-age=63072000; includeSubDomains"

async def dispatch(self, request, call_next):
    response = await call_next(request)
    if settings.environment != "local":       # never send over plain-http localhost
        response.headers["Strict-Transport-Security"] = HSTS
    return response
```

**Implementation Guidance:**
- Add the header to `frontend/vercel.json` and to the security headers middleware in `backend/app/core/security.py`, registered in `backend/app/main.py`.
- Use `max-age` of at least one year (63072000 = 2 years). Use `includeSubDomains` only when every subdomain of the custom domain serves HTTPS; on `*.vercel.app` it applies only to the project host.
- Add `preload` only after an explicit decision for a custom apex domain you control; it is hard to undo.
- Keep Vercel's automatic HTTP to HTTPS redirect; HSTS complements it. The SPA must use `https://` for `VITE_API_URL` and `VITE_SUPABASE_URL`, and `wss://` for Realtime.
- Reference: SD Elements guidance for T322.

**Success Criteria:**
- [ ] HTTPS responses from both deployments include `Strict-Transport-Security` with `max-age >= 31536000`.
- [ ] `frontend/.env.example` and `backend/.env.example` use only `https://` URLs.
- [ ] Verified by T333 tests.

**Status:** Applied
