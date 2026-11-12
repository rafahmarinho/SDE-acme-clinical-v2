---
name: t222-verify-server-to-server-authentication
description: Verification that every communicating pair in ACME Clinical (browser to Vercel frontend, frontend to FastAPI on Vercel, FastAPI to Supabase REST/Auth/Storage/Postgres, Vercel Cron to internal endpoints, Realtime) requires a credential and cannot be accessed or modified without one, verifying T10.
---

# T222: Verify server-to-server authentication

**Category:** CODE_FIX
**SD Elements:** [T222](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T222/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "README com os passos para rodar e publicar a versão web e a API na Vercel."
> (EN: README with the steps to run and publish the web version and the API on Vercel.)
> Source: specs/PRD.md, line 49

**What the spec implies (naive approach):**
The deployment has many components: the web app and API on separate Vercel projects, plus Supabase Postgres, Auth, Storage and Realtime. Without verification, an unauthenticated route (a forgotten router, an open storage bucket, a table without RLS) could let anyone on the internet read or change patient data.

**Secure Implementation Pattern:**
```python
# backend/tests/test_s2s_auth_matrix.py
import pytest
from app.main import app

PUBLIC = {"/health", "/docs", "/openapi.json"}       # remove docs in production (see T589)

def all_routes():
    return [(r.path, m) for r in app.routes if hasattr(r, "methods")
            for m in r.methods if m != "HEAD" and r.path not in PUBLIC]

@pytest.mark.parametrize("path,method", all_routes())
async def test_every_route_requires_credentials(client, path, method):
    r = await client.request(method, path.replace("{", "x").replace("}", ""))
    assert r.status_code in (401, 403, 405, 422), f"{method} {path} reachable without auth"
```
```sql
-- supabase/tests/rls_enabled.test.sql : no table reachable without RLS
select is((select count(*) from pg_tables
           where schemaname = 'public' and not rowsecurity), 0::bigint, 'RLS on all public tables');
select is((select count(*) from storage.buckets where public), 0::bigint, 'no public buckets');
```

**Implementation Guidance:**
- Step 1, inventory the components and endpoints: frontend Vercel URL, backend Vercel URL, Supabase `https://<ref>.supabase.co` (REST, Auth, Storage, Realtime), the Postgres pooler host, and Vercel Cron.
- Step 2, for each pair, confirm the credential: the user JWT (frontend to API), the service role key (API to Supabase), the DB password plus TLS (API to Postgres), and `CRON_SECRET` (Cron to API). With only the anon key, the REST API must return no rows because of RLS. Realtime channels must require an authenticated JWT (private channels with RLS on `realtime.messages`).
- Step 3, from another machine with no credentials: `curl` each backend route, `GET /rest/v1/patients` with only the anon key, and try listing the Storage buckets. Any data returned fails the test. Authentication must not depend on source IP, because Vercel and Supabase are reachable from the internet.
- Run the route matrix and RLS tests in CI. Do the manual curl checks against preview deployments.
- Reference: SD Elements guidance for T222.

**Success Criteria:**
- [ ] The route matrix test passes: every non-public route rejects unauthenticated requests.
- [ ] The RLS and storage pgTAP checks pass, and an anon-key-only REST query returns 0 patient rows.
- [ ] Results of the manual cross-machine curl test are recorded per release.

**Status:** Pending
