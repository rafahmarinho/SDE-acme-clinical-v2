---
name: t2597-implement-rbac-instead-of-individual-accounts
description: Assign ACME Clinical database privileges to PostgreSQL group roles and to application roles (nurse, physician, biomedical technician, administrator) evaluated in RLS, deny by default, instead of granting to individual accounts.
---

# T2597: Implement RBAC instead of individual accounts

**Category:** CODE_FIX
**SD Elements:** [T2597](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2597/)
**Priority:** 10/10 · **Phase:** deployment

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
Grants would be made directly to whichever login connects, and staff permissions hard-coded per user ID in policies. In Supabase all end users share the `authenticated` database role, so RBAC must be modeled in tables and checked by helper functions used in RLS.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0003_rbac.sql
create type public.app_role as enum ('nurse','physician','biomedical_technician','administrator');

create table security.role_permissions (
  role public.app_role not null, permission text not null,
  primary key (role, permission));

create table public.staff (
  id uuid primary key references auth.users(id) on delete cascade,
  role public.app_role,                 -- null = no access until assigned (deny by default)
  active boolean not null default true);

create function public.has_permission(p text) returns boolean
  language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.staff s
                 join security.role_permissions rp on rp.role = s.role
                 where s.id = auth.uid() and s.active and rp.permission = p) $$;
revoke all on function public.has_permission(text) from public;
grant execute on function public.has_permission(text) to authenticated, acme_api_rw;

-- seed (supabase/seed.sql): same matrix as backend/app/core/security.py
insert into security.role_permissions values
  ('nurse','patient:read'),('nurse','observation:write'),('nurse','alarm:ack'),
  ('physician','patient:read'),('physician','observation:write'),('physician','alarm:ack'),
  ('physician','threshold:write'),('biomedical_technician','device:manage'),
  ('biomedical_technician','monitor:bind'),('administrator','staff:manage'),
  ('administrator','simulation:reset');

create policy thresholds_update on clinical.alarm_thresholds for update to authenticated
  using (public.has_permission('threshold:write')) with check (public.has_permission('threshold:write'));
```

**Implementation Guidance:**
- Database-level: privileges go to NOLOGIN group roles (`acme_api_rw`, `acme_sim_rw`); login roles only inherit them (T2617, T2664).
- Application-level: roles and permissions live in `security.role_permissions`; RLS policies call `has_permission()`; never `auth.uid() = '<uuid>'` literals.
- Deny by default: `revoke all ... from public, anon, authenticated` on every schema/table, then grant explicitly; every table has RLS enabled (T2619).
- Keep granularity at the operation level (`threshold:write` vs `patient:read`) and column level where needed (T2607).
- Keep the Python matrix in `backend/app/core/security.py` and this table in sync via a test.
- Reference: SD Elements guidance for T2597.

**Success Criteria:**
- [ ] No table grant names an individual login role (query `information_schema.role_table_grants`).
- [ ] RLS policies reference only `has_permission()`/scope helpers.
- [ ] Staff with `role is null` can read nothing.

**Status:** Applied
