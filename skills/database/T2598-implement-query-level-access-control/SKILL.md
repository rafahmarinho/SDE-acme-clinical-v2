---
name: t2598-implement-query-level-access-control
description: Implement query-level access control in ACME Clinical's Supabase PostgreSQL with an access matrix per role, row-level security on every table, column grants for sensitive cells, and restricted function execution, so permissions live on the database objects themselves.
---

# T2598: Implement query-level access control

**Category:** CODE_FIX
**SD Elements:** [T2598](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T2598/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: loss of connection. Have nurse, physician, biomedical technician and administrator profiles.)
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
Role checks are written only in Python, while the database grants the API role full access to all tables and Supabase's `authenticated` role can query tables directly through PostgREST and Realtime. A biomedical technician's token can then read patient observations straight from `/rest/v1/observations`, and any backend bug exposes every row and column.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0003_authz_rbac.sql (pattern)
alter table public.observations enable row level security;
alter table public.observations force row level security;

create policy observations_select on public.observations for select to acme_api_rw
  using (public.has_permission('patients:read') and public.can_access_patient(patient_id));
create policy observations_insert on public.observations for insert to acme_api_rw
  with check (public.has_permission('observations:write')
              and public.can_access_patient(patient_id)
              and recorded_by = public.current_staff_id());

-- Column-level: only administrators' report path may read staff emails
revoke select on public.staff_profiles from acme_api_rw;
grant select (id, full_name, role, active) on public.staff_profiles to acme_api_rw;
grant select (id, full_name, role, active, email) on public.staff_profiles to acme_reporting;

-- Realtime only for rows the subscriber may see
create policy alarms_realtime on public.alarms for select to authenticated
  using (public.can_access_patient(patient_id));
```

**Implementation Guidance:**
- Write and maintain an access matrix (role/process x table/column/function x select/insert/update/delete) in `docs/security/authorization.md`; include `acme_api_rw`, `acme_reporting`, `acme_reset_owner`, `authenticated`, `anon`, the simulation process and device identities.
- Enable and force RLS on every table in `supabase/migrations/0001_schema.sql`..`0008_integration.sql`; write policies per operation using `has_permission`, `can_access_ward`, `can_access_patient`, `current_staff_id`.
- Use column grants for sensitive cells (staff email, monitor `secret_hash`, patient identifiers) and views/RPCs that return only needed columns.
- Restrict `execute` on functions to the roles that need them; `security definer` functions validate the caller's permission inside.
- `backend/app/db.py` `transaction(principal)` must set the request claims (`set_config('request.jwt.claims', ...)`) so policies evaluate the real user.
- Reference: SD Elements guidance for T2598.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_database_policies.py`): `select relname from pg_class where relrowsecurity = false` over `public` tables returns nothing.
- [ ] Policy tests per role: biomedical technician claims cannot select `observations`; nurse claims cannot select `staff_profiles.email`; `anon` selects nothing.
- [ ] The access matrix document matches grants (`information_schema.role_table_grants` / `column_privileges` snapshot test).

**Status:** Applied
