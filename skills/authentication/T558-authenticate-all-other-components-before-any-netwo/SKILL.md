---
name: t558-authenticate-all-other-components-before-any-netwo
description: Make every ACME Clinical component (React SPA, FastAPI API, Supabase PostgreSQL, Auth, Storage, Realtime and simulated monitors) authenticate the peer it talks to - verified TLS endpoints, JWT signature checks and per-device secrets - before exchanging any clinical data.
---

# T558: Authenticate all other components before any network communication with them

**Category:** CODE_FIX
**SD Elements:** [T558](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T558/)
**Priority:** 9/10 · **Phase:** requirements

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
With the frontend, the API and Supabase on separate hosts, a quick build lets the API connect to Postgres with `sslmode=require` (encrypted but not verifying the server), trusts any JWT that decodes, accepts readings from any caller that names a monitor ID, and lets the SPA call whatever API URL is in an environment variable. Each hop then trusts its peer implicitly.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py - the API authenticates the database server
@field_validator("database_url")
@classmethod
def _require_tls(cls, value: SecretStr) -> SecretStr:
    modes = parse_qs(urlsplit(value.get_secret_value()).query).get("sslmode", [])
    if modes != ["verify-full"]:
        raise ValueError("DATABASE_URL must enforce TLS with certificate verification (sslmode=verify-full)")
    return value

# backend/app/services/privacy.py - the API authenticates Supabase (HTTPS + verified certificate)
def _supabase_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=str(get_settings().supabase_url).rstrip("/"), timeout=10, verify=True)

# backend/app/core/security.py - the API authenticates callers: JWT signature, audience, issuer
claims = jwt.decode(token, key, algorithms=["HS256"], audience="authenticated",
                    issuer=f"{settings.supabase_url}/auth/v1", options={"require": ["exp", "sub", "session_id"]})
```

**Implementation Guidance:**
- API -> PostgreSQL: `DATABASE_URL` must use `sslmode=verify-full` (validator in `backend/app/core/config.py`, pool in `backend/app/db.py`) and a dedicated login role, never the `postgres` superuser.
- API -> Supabase Auth/Storage Admin: only `https://` URLs (`_https_outside_local_development`), `verify=True` on every `httpx` client (`backend/app/services/privacy.py`, `backend/app/routers/files.py` `_storage_client`, `backend/app/routers/staff.py` `supabase_admin_client`, `backend/app/cli.py`); never `verify=False`.
- Browser -> API and Supabase: the SPA only connects to origins pinned in the CSP `connect-src` in `frontend/vercel.json`; tokens are sent only to `VITE_API_URL` (`frontend/src/services/api.ts`).
- Caller -> API: every non-public route validates the Supabase JWT signature, `aud`, `iss`, `exp` and an active session (`backend/app/core/security.py`, `supabase/migrations/0005_sessions.sql`); spoofable headers (`X-Forwarded-For`, role headers) are not identity.
- Monitor -> API: each simulated monitor presents its own secret, verified with `verify_monitor_secret` (`backend/app/services/device_auth.py`, `0006_auth.sql`) before any reading is accepted.
- Reference: SD Elements guidance for T558.

**Success Criteria:**
- [ ] `backend/tests/test_authentication.py::test_database_connection_requires_tls_and_dedicated_role` and `test_outbound_http_clients_verify_tls` pass.
- [ ] `test_every_non_public_route_requires_credentials` and `test_invalid_tokens_rejected` (wrong signature, wrong audience/issuer, expired, `alg=none`) pass.
- [ ] `test_origin_ip_and_role_headers_are_not_authentication` passes.
- [ ] Pytest: a reading for a monitor without a valid device secret is rejected before any database write.

**Status:** Applied
