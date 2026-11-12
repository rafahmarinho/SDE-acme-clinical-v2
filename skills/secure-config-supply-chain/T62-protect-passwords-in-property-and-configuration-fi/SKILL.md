---
name: t62-protect-passwords-in-property-and-configuration-fi
description: Keep ACME Clinical secrets (Supabase service role key, JWT secret, database URL, cron secret) out of config files and git by loading them only from Vercel/OS environment variables via pydantic-settings, with placeholder-only .env.example files.
---

# T62: Protect passwords in property and configuration files

**Category:** CODE_FIX
**SD Elements:** [T62](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T62/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: complete, database configuration, initial data, environment variable examples and a)
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
"Exemplos de variáveis de ambiente" often turns into a committed `.env` with real keys, a `config.py` with a default service role key, or `vercel.json` with secrets in `env`. Putting the service role key in a `VITE_` variable exposes it in the browser bundle and bypasses all RLS.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")  # .env is git-ignored, local dev only
    app_env: str = "production"
    supabase_url: str
    supabase_service_role_key: SecretStr = Field(min_length=20)   # no default
    database_url: SecretStr
    cron_secret: SecretStr = Field(min_length=32)

settings = Settings()   # fails fast at startup if a secret is missing or empty
```

```bash
# backend/.env.example  (placeholders only, committed)
APP_ENV=development
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<set-in-vercel-env-never-commit>
DATABASE_URL=<set-in-vercel-env-never-commit>
CRON_SECRET=<generate: python -c "import secrets;print(secrets.token_urlsafe(48))">
# frontend/.env.example
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<public-anon-key>
VITE_API_BASE_URL=https://<api-project>.vercel.app
```

**Implementation Guidance:**
- Load all secrets in `backend/app/core/config.py` from environment variables with `SecretStr` and no defaults; empty strings fail validation.
- Store real values in Vercel project Environment Variables (marked Sensitive), per environment; local dev uses a git-ignored `.env`.
- Frontend only receives `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`; add a build check failing if any `VITE_*SERVICE*` or `VITE_*SECRET*` variable exists.
- Add `.env`, `.env.*` (except `.env.example`) to `.gitignore`; run gitleaks/`trufflehog` in CI and a pre-commit hook.
- Never put secrets in `backend/vercel.json`, `frontend/vercel.json` or `supabase/seed.sql`; never log `Settings` values.
- Reference: SD Elements guidance for T62.

**Success Criteria:**
- [ ] Backend startup fails when a required secret is missing or empty.
- [ ] No secrets in git (gitleaks scan clean); `.env.example` files contain placeholders only.
- [ ] Built frontend bundle contains no service role key (grep test in CI).
- [ ] README documents where each secret is configured.

**Status:** Pending
