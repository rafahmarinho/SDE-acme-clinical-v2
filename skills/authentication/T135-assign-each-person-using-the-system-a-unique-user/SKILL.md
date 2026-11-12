---
name: t135-assign-each-person-using-the-system-a-unique-user
description: Ensures every ACME Clinical nurse, physician, biomedical technician and administrator has an individual Supabase Auth account (unique UUID and email) linked to one profile row, with no shared ward, demo or admin accounts, as required for health data accountability.
---

# T135: Assign each person using the system a unique user ID

**Category:** CODE_FIX
**SD Elements:** [T135](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T135/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe"
> (EN: limit settings, reports and team management)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
To keep the demo simple, a developer might seed one login per role ("nurse@acme", "admin@acme") and let a whole ward share it. Then alarm acknowledgements, observations and monitor-to-bed bindings cannot be traced to a person, which breaks HIPAA-style accountability.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql
create type public.staff_role as enum ('nurse','physician','biomedical_technician','administrator');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete restrict,  -- 1 person = 1 auth user
  email text not null,
  full_name text not null,
  employee_number text not null,
  role public.staff_role not null,
  is_active boolean not null default true,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now()
);
create unique index profiles_email_uq on public.profiles (lower(email));
create unique index profiles_employee_uq on public.profiles (employee_number);

-- every clinical action records the individual actor
alter table public.alarm_acknowledgements
  add column acknowledged_by uuid not null references public.profiles(id) default auth.uid();
alter table public.observations
  add column author_id uuid not null references public.profiles(id) default auth.uid();
```

**Implementation Guidance:**
- Create accounts only through the administrator team-management endpoint in `backend/app/routers/` (Admin API `invite_user_by_email`). It inserts the `profiles` row in the same operation and requires a unique employee number.
- Never create generic accounts (`ward3@`, `admin@`). Each administrator gets their own account, and the Supabase dashboard owner account is not an app administrator.
- Stamp `auth.uid()` (or `claims["sub"]` in FastAPI) on alarm acknowledgements, observations, device bindings, limit changes and simulation actions. Do not take the actor ID from the client.
- Demo data: seed distinct fictional staff (for example one account per role with a named fictional person), each with its own invitation (see T61).
- Add a policy note in the README and the login screen footer: accounts are personal and must not be shared.
- Reference: SD Elements guidance for T135.

**Success Criteria:**
- [ ] `profiles` has unique `lower(email)` and `employee_number` constraints, and every row maps to exactly one `auth.users` row.
- [ ] Audit columns on clinical tables are `NOT NULL` and filled from `auth.uid()`. A SQL test inserts with a spoofed actor ID and checks that it is rejected or overwritten.
- [ ] No seed or fixture creates a role-named shared account.

**Status:** Pending
