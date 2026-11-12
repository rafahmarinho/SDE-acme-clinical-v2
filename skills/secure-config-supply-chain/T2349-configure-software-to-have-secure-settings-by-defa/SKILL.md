---
name: t2349-configure-software-to-have-secure-settings-by-defa
description: Make ACME Clinical secure by default as configuration-as-code - APP_ENV defaults to production (docs/debug off, strict CORS, security headers), simulation reset restricted, Supabase RLS on for every table, and every setting documented.
---

# T2349: Configure software to have secure settings by default

**Category:** CODE_FIX
**SD Elements:** [T2349](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2349/)
**Priority:** 8/10 · **Phase:** deployment

**Spec Context:**
> "README com os passos para rodar e publicar a versão web e a API na Vercel. Confira os fluxos"
> (EN: README with the steps to run and publish the web version and the API on Vercel. Check the main)
> Source: specs/PRD.md, line 49

**What the spec implies (naive approach):**
Quick-start configs usually default to development: FastAPI `/docs` and `/openapi.json` public, `debug=True` with stack traces, `allow_origins=["*"]`, and the "reset data" simulation endpoint open to any user. If someone forgets to set an env var in Vercel, production inherits these insecure defaults.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    app_env: str = "production"                       # secure unless explicitly dev
    allowed_origins: list[str] = []                   # none by default
    enable_docs: bool = False
    allow_simulation_reset: bool = False              # demo deployments opt in
    session_idle_minutes: int = 15

# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

dev = settings.app_env == "development"
app = FastAPI(debug=False,
              docs_url="/docs" if dev or settings.enable_docs else None,
              redoc_url=None,
              openapi_url="/openapi.json" if dev or settings.enable_docs else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                   allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"])

@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
                         "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
                         "Cache-Control": "no-store"})
    return resp
```

**Implementation Guidance:**
- Define all security settings in `backend/app/core/config.py` with secure defaults; development relaxations require explicit `APP_ENV=development`.
- Generic error handler in `backend/app/core/errors.py` (no stack traces); restrict simulation reset to administrators and `allow_simulation_reset`.
- `supabase/migrations/0001_schema.sql`: `enable row level security` on every table, revoke default `anon` grants, private Storage buckets by default.
- Security headers/CSP in `frontend/vercel.json` and `backend/vercel.json`.
- Document every setting (purpose, options, default, security relevance, impact, dependencies) in `docs/security/configuration.md`; changes go through PR review (configuration as code).
- Reference: SD Elements guidance for T2349.

**Success Criteria:**
- [ ] With no env overrides, `/docs` and `/openapi.json` return 404 and CORS allows no origins.
- [ ] All tables have RLS enabled; Storage buckets are private.
- [ ] Configuration reference documents each setting.
- [ ] T2357 tests pass.

**Status:** Pending
