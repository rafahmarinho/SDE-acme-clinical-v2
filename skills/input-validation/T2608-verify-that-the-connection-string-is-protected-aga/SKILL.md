---
name: t2608-verify-that-the-connection-string-is-protected-aga
description: Test recipe verifying that ACME Clinical's Supabase/PostgreSQL connection strings and keys come only from environment variables, are never built from user input, never appear in URLs, logs or the frontend bundle, and are protected against connection string parameter pollution.
---

# T2608: Verify that the connection string is protected against connection string parameter pollution

**Category:** CODE_FIX
**SD Elements:** [T2608](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2608/)
**Priority:** 9/10 · **Phase:** testing

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: "complete, database configuration, initial data, environment variable examples and a")
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
The deliverable includes database configuration and env var examples. A developer may hard-code a fallback `postgresql://postgres:password@...` in `backend/app/db.py`, commit real values in `.env.example`, append user-chosen options (e.g. a "database" or "schema" selector for simulation reset) to the DSN, or log the DSN on startup errors.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py
from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None)   # Vercel env vars only in prod
    database_url: PostgresDsn                           # required, no default
    supabase_service_role_key: SecretStr

settings = Settings()

# backend/app/db.py
import psycopg_pool
pool = psycopg_pool.AsyncConnectionPool(conninfo=str(settings.database_url), open=False,
                                        kwargs={"options": "-c statement_timeout=5000"})

# backend/tests/test_connection_string.py
import re, pathlib, logging
DSN = re.compile(r"postgres(ql)?://[^\s'\"]+:[^\s'\"]+@")
def test_no_hardcoded_dsn():
    for p in pathlib.Path(".").rglob("*"):
        if p.suffix in {".py", ".ts", ".tsx", ".json", ".sql", ".example"} and "node_modules" not in p.parts:
            assert not DSN.search(p.read_text(errors="ignore")), p

def test_dsn_not_logged(caplog, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:SeCrEt@h:5432/d")
    caplog.set_level(logging.DEBUG)
    from app.core.config import Settings; s = Settings()
    assert "SeCrEt" not in repr(s) and "SeCrEt" not in caplog.text
```

**Implementation Guidance:**
- Confirm `DATABASE_URL`, `SUPABASE_URL` and keys are loaded only from env vars (Vercel project settings); `.env.example` files contain placeholders only; `.env` is gitignored.
- Confirm no DSN or option is constructed from request data; any per-request choice (e.g. simulation dataset) maps to server-side constants, never DSN parameters. If a value must ever enter a DSN, reject `;`, `&`, `=`, spaces and quotes, or pass it as a separate `psycopg.connect(**kwargs)` keyword.
- Verify connection strings never appear in URLs, error responses or logs (`backend/app/core/logging.py` redaction filter); use `SecretStr` for keys.
- Verify the frontend bundle contains only `VITE_SUPABASE_URL` and the anon key: run `pnpm build` and grep `dist/` for `service_role` and `postgres://`.
- Check file access: env files are not served by Vercel (`frontend/vercel.json`/`backend/vercel.json` do not expose them).
- Reference: SD Elements guidance for T2608.

**Success Criteria:**
- [ ] `backend/tests/test_connection_string.py` passes (no hard-coded DSNs, not logged).
- [ ] Frontend build grep finds no service-role key or PostgreSQL DSN.
- [ ] Code search shows no DSN built with f-strings from request input.

**Status:** Pending
