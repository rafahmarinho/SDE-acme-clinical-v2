---
name: t257-secure-cross-origin-resource-sharing-cors
description: Secure CORS between the separately deployed ACME Clinical frontend and API on Vercel with an exact-match origin allowlist from configuration (no wildcard, no suffix matching of *.vercel.app), explicit methods/headers, bounded Max-Age, and authentication that never depends on the Origin header.
---

# T257: Secure cross origin resource sharing (CORS)

**Category:** CODE_FIX
**SD Elements:** [T257](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T257/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
Publishing the web app and API separately forces cross-origin calls. The typical "make it work" fix is `allow_origins=["*"]` or `allow_origin_regex=r"https://.*\.vercel\.app"`, which lets any Vercel-hosted site (including an attacker's) read API responses with a victim's token flow, and preview deployments become trusted origins.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py
class Settings(BaseSettings):
    cors_origins: list[AnyHttpUrl] = []          # e.g. ["https://acme-clinical.vercel.app"], from env

    @field_validator("cors_origins")
    @classmethod
    def _exact_https(cls, v):
        for o in v:
            if "*" in str(o) or (o.scheme != "https" and o.host not in ("localhost", "127.0.0.1")):
                raise ValueError("CORS origins must be exact https origins")
        return v

# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(o).rstrip("/") for o in settings.cors_origins],   # exact string match
    allow_origin_regex=None,
    allow_credentials=False,                     # bearer tokens, no cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["Retry-After", "X-Request-ID"],
    max_age=600,
)
```

**Implementation Guidance:**
- Configure `CORS_ORIGINS` per environment in Vercel (production custom domain; optionally one fixed preview domain) and in `backend/.env.example`; never derive allowed origins from the request.
- Use exact matching only (no `startswith`/`endswith`/regex on `*.vercel.app`); reject `null` origin.
- Keep `allow_credentials=False` since the frontend authenticates with `Authorization` headers (`frontend/src/services/api.ts`); if credentials are ever needed, never combine with wildcard.
- Authentication/authorization (`backend/app/core/security.py`) applies to every method except preflight `OPTIONS`; CORS is not access control.
- Do not emit CORS headers on routes not meant for cross-origin use (e.g. `/csp-report` accepts browser reports without credentials).
- The host header allowlist (`DEFAULT_ALLOWED_HOSTS` in `backend/app/core/middleware.py`) should also be the exact API host(s) in production rather than `*.vercel.app`.
- Reference: SD Elements guidance for T257.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_api_security.py`): preflight from `https://evil.vercel.app` and `null` returns no `Access-Control-Allow-Origin`; from the configured origin returns that exact origin and `Access-Control-Max-Age: 600`.
- [ ] `Settings` refuses `*` or regex-like values for `CORS_ORIGINS`.
- [ ] No response includes `Access-Control-Allow-Credentials: true` together with a wildcard.

**Status:** Applied
