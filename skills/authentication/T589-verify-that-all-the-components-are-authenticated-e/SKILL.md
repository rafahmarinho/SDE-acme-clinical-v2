---
name: t589-verify-that-all-the-components-are-authenticated-e
description: Verification that each ACME Clinical component explicitly authenticates its peers before exchanging data (no implicit trust of the frontend origin, internal network, simulated monitors or forwarded headers), covering FastAPI, Supabase, Vercel Cron and the simulated device feed.
---

# T589: Verify that all the components are authenticated explicitly

**Category:** CODE_FIX
**SD Elements:** [T589](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T589/)
**Priority:** 9/10 · **Phase:** testing

**Spec Context:**
> "Quero as telas funcionando e os dados persistidos, com integrações externas simuladas."
> (EN: I want the screens working and the data persisted, with simulated external integrations.)
> Source: specs/PRD.md, lines 7-9

**What the spec implies (naive approach):**
Because the external integrations are "simulated", developers tend to treat them as trusted: the simulator posts readings without credentials, the API trusts requests whose `Origin` is the frontend, or it trusts `X-User-Role` headers. Simulated components still cross the network and must authenticate explicitly.

**Secure Implementation Pattern:**
```python
# backend/tests/test_explicit_component_auth.py
import pytest
from tests.jwt_factory import make_token

async def test_origin_header_is_not_authentication(client):
    r = await client.get("/patients", headers={"Origin": "https://acme-clinical.vercel.app"})
    assert r.status_code == 401

async def test_spoofed_identity_headers_ignored(client):
    tok = make_token(role="nurse")
    r = await client.get("/admin/staff", headers={"Authorization": f"Bearer {tok}",
                                                  "X-User-Role": "administrator",
                                                  "X-Forwarded-For": "127.0.0.1"})
    assert r.status_code == 403

async def test_unsigned_device_reading_rejected(client):
    r = await client.post("/internal/readings", json={"device_id": "MON-01", "hr": 72},
                          headers={"Authorization": "Bearer <valid-cron-secret>"})
    assert r.status_code == 401          # device signature required (T425)

async def test_docs_disabled_in_production(prod_client):
    assert (await prod_client.get("/docs")).status_code == 404
```

**Implementation Guidance:**
- List every connection and its explicit authentication:
  - Browser to Supabase: anon key plus user JWT, enforced by RLS.
  - Frontend to FastAPI: a verified JWT (T10). CORS is not authentication.
  - FastAPI to Supabase: service key over HTTPS. FastAPI to Postgres: password with `sslmode=require`.
  - Vercel Cron to `/internal/*`: `CRON_SECRET`.
  - Simulated monitors to ingest: a per-device signature (T425).
  - Realtime: private channels that require a JWT.
- Grep `backend/app/` for decisions based on `request.client.host`, `Origin`, `Referer` or custom `X-*` headers. None may grant access.
- Disable FastAPI docs in production (`FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` when `settings.env == "production"`), or put them behind auth.
- Confirm that the backend validates Supabase TLS certificates (default httpx verification on; never `verify=False`).
- Reference: SD Elements guidance for T589.

**Success Criteria:**
- [ ] The tests above pass. No access is granted based on origin, IP or spoofable headers.
- [ ] The component authentication inventory is documented in the README, and each entry has a test.
- [ ] A grep for `verify=False` in `backend/` returns nothing.

**Status:** Applied
