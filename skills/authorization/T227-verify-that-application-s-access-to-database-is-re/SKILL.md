---
name: t227-verify-that-application-s-access-to-database-is-re
description: Verify that the ACME Clinical FastAPI backend connects to Supabase PostgreSQL with a dedicated least-privilege role (acme_api), not postgres or service_role, and that this role cannot run DDL, delete records or bypass RLS.
---

# T227: Verify that application's access to database is restricted

**Category:** CODE_FIX
**SD Elements:** [T227](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T227/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: "...complete code, database configuration, initial data, environment variable examples and a")
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
The quickest path is to paste the Supabase `postgres` connection string or the `service_role` key into `backend/.env` and the Vercel project. That account owns the schema and bypasses RLS, so any SQL injection or logic bug in the API has full database power.

**Secure Implementation Pattern:**
```sql
-- supabase/tests/app_db_access.sql (pgTAP, run with `supabase test db`)
begin;
select plan(7);
select is((select rolsuper from pg_roles where rolname = 'acme_api'), false, 'not superuser');
select is((select rolbypassrls from pg_roles where rolname = 'acme_api'), false, 'no BYPASSRLS');
select is((select rolcreaterole or rolcreatedb from pg_roles where rolname = 'acme_api'), false, 'no create role/db');
select ok(not has_schema_privilege('acme_api', 'clinical', 'CREATE'), 'no DDL in clinical');
select ok(not has_table_privilege('acme_api', 'clinical.patients', 'DELETE'), 'no DELETE on patients');
select ok(not has_table_privilege('acme_api', 'audit.events', 'UPDATE'), 'audit append-only');
select is((select count(*)::int from pg_tables t where t.tableowner = 'acme_api'), 0, 'owns nothing');
select * from finish();
rollback;
```
```python
# backend/tests/test_db_account.py
from urllib.parse import urlparse

def test_runtime_db_user_is_acme_api(settings):
    assert urlparse(str(settings.database_url)).username.split(".")[0] == "acme_api"  # pooler: acme_api.<ref>
    assert "service_role" not in settings.model_dump_json()
```

**Implementation Guidance:**
- Review `backend/app/db.py` and `backend/app/core/config.py` to identify the connection account; `backend/.env.example` must show `acme_api` (see T2617 for the role migration).
- Run the pgTAP test in CI against a local Supabase (`supabase start` + `supabase test db`).
- Confirm the Supabase `service_role` key is not used by request handlers; if it is needed (admin user invitation), isolate it in one admin-only function.
- Review `\du+` output on the hosted project and record it.
- Reference: SD Elements guidance for T227.

**Success Criteria:**
- [ ] pgTAP test passes; `acme_api` has no superuser, BYPASSRLS, DDL, DELETE or ownership.
- [ ] Config test confirms the runtime user is `acme_api`.
- [ ] `\du+` review of the hosted project documented.

**Status:** Pending
