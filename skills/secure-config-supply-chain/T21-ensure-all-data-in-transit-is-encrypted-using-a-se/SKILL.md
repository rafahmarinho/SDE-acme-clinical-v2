---
name: t21-ensure-all-data-in-transit-is-encrypted-using-a-se
description: Ensure every ACME Clinical hop - browser to Vercel SPA and API, API to Supabase PostgreSQL/Auth/Storage, Realtime websockets - uses TLS 1.2+ with verified certificates, HSTS and no plaintext fallback, and that TLS failures are logged.
---

# T21: Ensure all data in transit is encrypted using a secure TLS channel

**Category:** CODE_FIX
**SD Elements:** [T21](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T21/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
Login, file transfers and live vital-sign streams cross the internet between three hosts. Typical shortcuts are an `http://` API URL in `VITE_API_URL`, a Realtime client on `ws://`, `sslmode=prefer` for Postgres, and CORS/redirect rules that accept plain-HTTP origins - each exposing credentials or patient data to eavesdroppers.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py - https:// only outside local development, verified DB TLS
@model_validator(mode="after")
def _https_outside_local_development(self) -> "Settings":
    def insecure(url: AnyHttpUrl) -> bool:
        return url.scheme != "https" and url.host not in {"localhost", "127.0.0.1"}
    if self.app_env != "development" and (insecure(self.supabase_url) or any(map(insecure, self.cors_allowed_origins))):
        raise ValueError("service URLs and CORS origins must use https://")
    return self
```
```json
// frontend/vercel.json - force HTTPS in browsers, upgrade any stray http:// subresource
{ "key": "Strict-Transport-Security", "value": "max-age=63072000; includeSubDomains" },
{ "key": "Content-Security-Policy", "value": "...; connect-src 'self' https://<api> https://<ref>.supabase.co wss://<ref>.supabase.co; upgrade-insecure-requests" }
```

**Implementation Guidance:**
- Browser hops: Vercel serves only HTTPS (TLS 1.2/1.3, platform-managed ciphers); keep HSTS and `upgrade-insecure-requests` in `frontend/vercel.json` and add the same HSTS header on API responses (`backend/app/core/middleware.py`); CSP `connect-src` lists only `https://` and `wss://` origins.
- Frontend config: `VITE_API_URL` and `VITE_SUPABASE_URL` must be `https://` in production builds - validate in `frontend/src/lib/supabase.ts` / `frontend/src/services/api.ts` and fail fast otherwise; Realtime (`frontend/src/hooks/useRealtime.ts`) uses `wss://` derived from the HTTPS URL.
- Server hops: `DATABASE_URL` with `sslmode=verify-full` (`backend/app/core/config.py`, `backend/app/db.py`); `httpx` clients with `verify=True` (see T156).
- Refuse plaintext authentication: the API never accepts credentials over HTTP (Vercel redirects HTTP to HTTPS; the API rejects non-HTTPS `X-Forwarded-Proto` in production).
- Log TLS/connection failures to the database and Supabase as security events (`backend/app/core/logging.py`).
- Protocol/cipher configuration and certificate management on Vercel and Supabase endpoints are platform-managed (INFRA; see cloud-infrastructure T2290/T2365).
- Reference: SD Elements guidance for T21.

**Success Criteria:**
- [ ] `backend/tests/test_secure_config.py::test_t175_service_urls_must_be_https` and `test_t175_database_tls_must_verify_certificates` pass.
- [ ] `backend/tests/test_secure_config.py::test_t2357_security_headers_on_every_response` asserts HSTS on API responses.
- [ ] Vitest: building with `VITE_API_URL=http://api.example.com` in production mode throws.
- [ ] Manual check: `testssl.sh` against the frontend and API domains shows only TLS 1.2/1.3 and no compression.

**Status:** Applied
