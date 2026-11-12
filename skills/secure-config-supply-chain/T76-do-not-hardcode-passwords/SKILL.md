---
name: t76-do-not-hardcode-passwords
description: Keep every ACME Clinical password, key and token (Supabase service role key, JWT secret, database URL, signing/HMAC keys, monitor secrets, demo account passwords) out of source, seed data, Vercel config and CI, loading them only from environment variables.
---

# T76: Do not hardcode passwords

**Category:** CODE_FIX
**SD Elements:** [T76](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T76/)
**Priority:** 10/10 · **Phase:** development

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> "README com os passos para rodar e publicar a versão web e a API na Vercel. Confira os fluxos"
> (EN: complete [code], database configuration, initial data, environment variable examples and a README with the steps to run and publish the web version and the API on Vercel. Check the flows)
> Source: specs/PRD.md, lines 47-49

**What the spec implies (naive approach):**
To make the demo "just work", developers put a default `SUPABASE_SERVICE_ROLE_KEY` in `config.py`, demo logins like `admin@acme.test / Admin123!` in `seed.sql` and the README, and real keys in `.env.example` or `vercel.json`. Anyone with repository access - or the public frontend bundle - then holds full database access.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py - required, no defaults, placeholders rejected, never printed
class Settings(BaseSettings):
    supabase_service_role_key: SecretStr          # no default value
    supabase_jwt_secret: SecretStr
    database_url: SecretStr

    @field_validator("supabase_service_role_key", "supabase_jwt_secret", "database_url")
    @classmethod
    def _not_empty_or_placeholder(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value().strip()
        if not raw or raw.startswith("<") or "changeme" in raw.lower():
            raise ValueError("secret must be provided via environment variable")
        return value
```
```bash
# backend/.env.example - placeholders only
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_JWT_SECRET=<jwt-secret>
```

**Implementation Guidance:**
- All secrets are `SecretStr` fields without defaults in `backend/app/core/config.py`, injected by Vercel Project > Settings > Environment Variables (marked Sensitive); `.env` files are git-ignored.
- `backend/.env.example` and `frontend/.env.example` contain only `<placeholder>` values; the frontend gets only `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` and `VITE_API_URL` - never the service role key, JWT secret or `DATABASE_URL`.
- `supabase/seed.sql` creates no auth users or passwords; demo staff accounts are created by `python -m app.cli` (`backend/app/cli.py`) with unique random one-time passwords, refused in production.
- Monitor device secrets are generated and stored hashed (`provision-monitor-secrets`), never committed.
- CI (`.github/workflows/ci.yml`) uses GitHub secrets and a secret scanner (e.g. gitleaks) on every push; README documents where each secret lives.
- Reference: SD Elements guidance for T76.

**Success Criteria:**
- [ ] `backend/tests/test_secure_config.py::test_t62_startup_fails_without_each_secret`, `test_t62_empty_or_placeholder_secrets_rejected` and `test_t62_secrets_never_appear_in_reprs` pass.
- [ ] `test_t62_env_examples_hold_placeholders_only_and_env_files_are_ignored` and `test_t62_no_secrets_in_vercel_configs_seed_or_ci` pass.
- [ ] `backend/tests/test_authentication.py::test_no_default_credentials_in_repo_artefacts` and `test_service_role_key_never_reaches_the_browser` pass.
- [ ] The CI secret scan reports no findings on the release commit.

**Status:** Pending
