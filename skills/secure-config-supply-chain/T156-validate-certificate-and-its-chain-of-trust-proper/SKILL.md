---
name: t156-validate-certificate-and-its-chain-of-trust-proper
description: Ensure every outbound TLS connection from the ACME Clinical API (Supabase PostgreSQL, Auth Admin, Storage) validates the full certificate chain, hostname and expiry, with no code path that disables verification.
---

# T156: Validate certificate and its chain of trust properly

**Category:** CODE_FIX
**SD Elements:** [T156](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T156/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current, stable versions of the technologies and Supabase for PostgreSQL, e-mail login and)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
Connecting a Vercel function to hosted Supabase PostgreSQL commonly uses the dashboard connection string with `sslmode=require`, which encrypts but accepts any certificate; when a certificate error appears during development, developers add `verify=False` to `httpx`. Either way a network attacker can impersonate the database or the Auth Admin API and capture the service role key or patient data.

**Secure Implementation Pattern:**
```python
# backend/app/db.py - libpq verifies chain + hostname against the Supabase CA bundle
pool = AsyncConnectionPool(
    conninfo=settings.database_url.get_secret_value(),       # ...?sslmode=verify-full
    kwargs={"sslrootcert": settings.database_ca_file or "system"},
    open=False,
)

# Every httpx client verifies with the system / certifi trust store
def _storage_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=str(get_settings().supabase_url).rstrip("/"),
                             timeout=timeout, verify=True)   # never verify=False

# On failure: fail closed and log, never retry without verification
except (ssl.SSLCertVerificationError, httpx.ConnectError) as exc:
    sec_event("tls_verification_failed", target="supabase", error=type(exc).__name__)
    raise ServiceUnavailable()
```

**Implementation Guidance:**
- Require `sslmode=verify-full` in `DATABASE_URL` (validator `_require_tls` in `backend/app/core/config.py`); provide the Supabase root CA via `sslrootcert` (download from the Supabase dashboard, store as an environment variable or bundled file) so chain and hostname are both checked.
- Keep `verify=True` on all `httpx.AsyncClient` instances (`backend/app/routers/files.py`, `backend/app/routers/staff.py`, `backend/app/services/privacy.py`, `backend/app/cli.py`) and use only `https://` service URLs (`_https_outside_local_development`).
- Expiry and revocation checking are provided by OpenSSL and the managed endpoints; keep `cryptography`, `httpx` and `psycopg` up to date (`backend/requirements.txt`, Dependabot) so validation bugs are patched.
- Log TLS verification failures as security events (`backend/app/core/logging.py` `acme.security`) and return a generic 503; do not fall back to plaintext or unverified TLS.
- Certificate issuance and rotation for `*.supabase.co` and `*.vercel.app` are managed by the platforms (INFRA).
- Reference: SD Elements guidance for T156.

**Success Criteria:**
- [ ] `backend/tests/test_secure_config.py::test_t175_database_tls_must_verify_certificates` rejects `sslmode=require`, `prefer` and missing `sslmode`.
- [ ] `test_t175_tls_verification_never_disabled_in_source` finds no `verify=False`, `CERT_NONE` or `check_hostname = False` in `backend/`.
- [ ] Manual check: pointing `SUPABASE_URL` at a host with a self-signed certificate makes the API fail closed with 503 and a `tls_verification_failed` log entry.

**Status:** Applied
