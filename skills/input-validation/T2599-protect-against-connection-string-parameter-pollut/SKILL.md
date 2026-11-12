---
name: t2599-protect-against-connection-string-parameter-pollut
description: Protect ACME Clinical's PostgreSQL connection string (DATABASE_URL for the Supabase pooler) from parameter pollution by loading it only from environment configuration, never composing it from user input, validating its structure (sslmode, host, role) at startup and never logging it.
---

# T2599: Protect against connection string parameter pollution

**Category:** CODE_FIX
**SD Elements:** [T2599](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T2599/)
**Priority:** 9/10 · **Phase:** development

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: complete, database configuration, initial data, examples of environment variables and a)
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
The backend needs a PostgreSQL DSN for Supabase. Shortcuts include hardcoding it, assembling it from pieces (`f"postgresql://{user}:{pw}@{host}/{db}?{extra}"`) where some piece can be influenced (a "tenant"/ward parameter, an admin "database settings" screen), or logging it on connection errors. Appended parameters (`&sslmode=disable`, `&host=attacker`, `options=-c role=postgres`) can disable TLS, redirect the connection or escalate the role.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py
from urllib.parse import urlsplit, parse_qs
from pydantic import SecretStr, field_validator

ALLOWED_DSN_PARAMS = {"sslmode", "application_name", "connect_timeout"}

class Settings(BaseSettings):
    database_url: SecretStr                         # only from env (Vercel/`.env`), never from requests

    @field_validator("database_url")
    @classmethod
    def _validate_dsn(cls, v: SecretStr) -> SecretStr:
        parts = urlsplit(v.get_secret_value())
        if parts.scheme not in ("postgresql", "postgres"):
            raise ValueError("DATABASE_URL must be a postgresql:// URL")
        params = parse_qs(parts.query, strict_parsing=bool(parts.query))
        if set(params) - ALLOWED_DSN_PARAMS or any(len(x) != 1 for x in params.values()):
            raise ValueError("DATABASE_URL has unexpected or duplicated parameters")
        if params.get("sslmode", ["require"])[0] not in ("require", "verify-ca", "verify-full"):
            raise ValueError("DATABASE_URL must require TLS")
        if ";" in parts.netloc or "," in (parts.hostname or ""):
            raise ValueError("DATABASE_URL host list not allowed")
        return v
```

**Implementation Guidance:**
- Keep `DATABASE_URL` as a `SecretStr` in `backend/app/core/config.py`; it is set only via Vercel environment variables / local `.env` (documented with a placeholder in `backend/.env.example`).
- `backend/app/db.py` passes the DSN to `AsyncConnectionPool` unchanged; no code concatenates user, ward, tenant or request values into it. Per-request role changes use `set local role`/`set_config` with bound values, not DSN options.
- Validate structure at startup (scheme, single host, allowlisted parameters, TLS required, expected role such as `acme_api` rather than `postgres`; see `database_url_problems` in `backend/app/services/passwords.py`) and fail closed.
- Never log, return or echo the DSN: `backend/app/core/logging.py` redaction must cover `postgresql://user:pass@` patterns; exceptions from psycopg are mapped to a generic message in `backend/app/core/errors.py`.
- No admin UI or API endpoint accepts connection parameters.
- Reference: SD Elements guidance for T2599.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_secure_config.py`): `Settings` rejects DSNs with `sslmode=disable`, duplicated `host`, unknown `options=` and non-postgres schemes.
- [ ] Pytest (`backend/tests/test_logging_audit.py`): a log line containing a DSN is emitted with credentials redacted.
- [ ] No module other than `config.py`/`db.py` reads `DATABASE_URL`.

**Status:** Applied
