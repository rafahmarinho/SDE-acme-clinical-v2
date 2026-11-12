---
name: t2617-create-dedicated-database-user-accounts-with-minim
description: Create a dedicated non-superuser, non-owner PostgreSQL login role for the ACME Clinical FastAPI backend in a Supabase migration, granting only the SELECT/INSERT/UPDATE it needs and no DELETE, DDL or BYPASSRLS.
---

# T2617: Create dedicated database user accounts with minimum privileges (PostgreSQL)

**Category:** CODE_FIX
**SD Elements:** [T2617](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2617/)
**Priority:** 8/10 · **Phase:** deployment

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: "...complete code, database configuration, initial data, environment variable examples and a")
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
The PRD asks for the database configuration in the repo; the default Supabase setup hands out the `postgres` owner connection string, which is what the backend would use. That role owns all objects and can drop tables or disable RLS.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0002_app_roles.sql
-- Group role holds privileges; login role only inherits (see T2597).
create role acme_api_rw nologin;
create role acme_api login   -- password set out-of-band: ALTER ROLE acme_api PASSWORD ... (never committed)
  nosuperuser nocreatedb nocreaterole noreplication nobypassrls inherit
  connection limit 20 in role acme_api_rw, authenticated;   -- can SET ROLE authenticated for RLS (T18)
alter role acme_api set statement_timeout = '5s';

revoke all on schema public, clinical, devices, simulation, audit from public;
grant usage on schema clinical, devices, simulation, audit to acme_api_rw;

grant select, insert, update on clinical.patients, clinical.observations, clinical.alarms,
      clinical.alarm_thresholds to acme_api_rw;
grant select, insert, update on devices.monitors, devices.bed_assignments,
      devices.maintenance_tickets to acme_api_rw;
grant select, insert on simulation.events, audit.events to acme_api_rw;
grant usage on all sequences in schema clinical, devices, simulation, audit to acme_api_rw;
-- No DELETE / TRUNCATE / REFERENCES / TRIGGER; no CREATE on any schema; owns nothing.
-- Demo reset runs via a SECURITY DEFINER function owned by a separate role (see T2664).
```

**Implementation Guidance:**
- Add the migration under `supabase/migrations/` after `0001_schema.sql`; objects remain owned by `postgres` (migration owner), never by `acme_api`.
- Set the password at deploy time (`ALTER ROLE acme_api PASSWORD ...` run once in the Supabase SQL editor or CLI, not in a committed migration) and store the resulting connection string only in Vercel env vars; `backend/.env.example` shows `DATABASE_URL=postgresql://acme_api.<project-ref>:<password>@<pooler-host>:6543/postgres`.
- Use `pg_read_all_data` only for a separate reporting/read-only analyst role if one is needed, never for the API.
- Audit with `\du+` and `select * from information_schema.role_table_grants where grantee in ('acme_api','acme_api_rw')`.
- Reference: SD Elements guidance for T2617.

**Success Criteria:**
- [ ] `acme_api` is `NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB` and owns no objects.
- [ ] `acme_api` has no DELETE/TRUNCATE/DDL privileges (pgTAP test from T227).
- [ ] Backend connects successfully as `acme_api` and all API tests pass.

**Status:** Pending
