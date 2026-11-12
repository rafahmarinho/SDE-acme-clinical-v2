---
name: t19-restrict-application-s-access-to-database
description: Restrict the ACME Clinical backend's database access to dedicated least-privilege PostgreSQL roles (acme_api, acme_api_rw, acme_reporting) with only the schemas, tables, actions and functions they need, instead of the Supabase postgres or service_role superuser.
---

# T19: Restrict Application's Access to Database

**Category:** CODE_FIX
**SD Elements:** [T19](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T19/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current, stable versions of the technologies and Supabase for PostgreSQL, email and password login and)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
Supabase hands developers a `postgres` connection string and a `service_role` key; the default is to use them for the FastAPI backend. Any SQL injection or logic flaw then runs as a role that bypasses RLS, can drop tables, read `auth.users`, alter the audit log and execute every function.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0002_roles_rls.sql (pattern)
create role acme_api login password :'acme_api_password' noinherit nosuperuser nocreatedb nocreaterole nobypassrls;
create role acme_api_rw nologin nobypassrls;
create role acme_reporting nologin nobypassrls;
grant acme_api_rw, acme_reporting to acme_api;         -- switched per request with SET LOCAL ROLE

revoke all on schema public from public;
revoke all on all tables in schema public from public, anon, authenticated;
revoke execute on all functions in schema public from public;
grant usage on schema public to acme_api_rw, acme_reporting;

grant select on public.wards, public.beds, public.patients, public.monitors, public.readings to acme_api_rw;
grant select, insert on public.observations to acme_api_rw;                      -- no update/delete
grant select, update (acknowledged_at, acknowledged_by, ack_note) on public.alarms to acme_api_rw;
grant insert on public.events to acme_api_rw;                                     -- append-only audit
grant select on public.events to acme_reporting;
grant execute on function public.can_access_patient(uuid), public.has_permission(text) to acme_api_rw;
alter default privileges in schema public revoke all on tables from public;
```

**Implementation Guidance:**
- `DATABASE_URL` in `backend/.env.example`/Vercel uses the `acme_api` login role through the Supabase pooler, never `postgres`; `backend/app/db.py` `transaction()` does `set local role acme_api_rw` (or `acme_reporting` for read-only report paths).
- Grant per table and per action in `supabase/migrations/0002_roles_rls.sql`/`0003_authz_rbac.sql`; use column-level grants for updates; revoke `PUBLIC` execute on functions and grant only the RLS helper/RPC functions needed.
- Privileged operations (simulation reset, retention purge, session revocation) are `security definer` functions owned by a dedicated role (`acme_reset_owner`) with `set search_path = ''` and execute granted only to the API role, not to `authenticated`/`anon`.
- The `service_role` key is used only by the narrowly scoped Supabase Admin calls in `backend/app/services/privacy.py`; it must never reach the frontend.
- Startup check: refuse to run if the connected role is a superuser or has `rolbypassrls` (`database_url_problems` in `backend/app/services/passwords.py`).
- Reference: SD Elements guidance for T19.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_database_policies.py`): as `acme_api_rw`, `delete from public.events`, `update public.observations`, `select from auth.users` and `drop table` all fail with permission errors.
- [ ] `select rolsuper, rolbypassrls from pg_roles where rolname = current_user` is false/false at backend startup.
- [ ] Supabase advisors report no tables exposed to `anon`.

**Status:** Pending
