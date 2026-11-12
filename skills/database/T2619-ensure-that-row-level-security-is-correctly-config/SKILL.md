---
name: t2619-ensure-that-row-level-security-is-correctly-config
description: Enable and force RLS on every ACME Clinical Supabase table, write ward-scoped and permission-based policies for patients, vitals, alarms, observations, devices and staff, and ensure no application role has BYPASSRLS.
---

# T2619: Ensure that row-level security is correctly configured (PostgreSQL)

**Category:** CODE_FIX
**SD Elements:** [T2619](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2619/)
**Priority:** 7/10 · **Phase:** deployment

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: "...password, files and real-time updates. I want the screens working and the data")
> Source: specs/PRD.md, line 7

> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: "ward view, patient list and detail, live monitoring, alarms, devices,")
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
Supabase Realtime and the browser client query tables directly with the public anon key. Tables created without RLS (or with `using (true)` policies) stream every patient's vitals and alarms to any logged-in user, or to anyone with the anon key.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0005_rls.sql
create function public.can_access_patient(p_patient uuid) returns boolean
  language sql stable security definer set search_path = '' as $$
  select exists (select 1 from clinical.patients p
                 join public.staff_wards sw on sw.ward_id = p.ward_id
                 join public.staff s on s.id = sw.staff_id and s.active
                 where p.id = p_patient and sw.staff_id = auth.uid())
      or exists (select 1 from security.break_glass_grants g
                 where g.user_id = auth.uid() and g.patient_id = p_patient
                   and g.revoked_at is null and g.expires_at > now()) $$;

do $$ declare t text; begin
  foreach t in array array['clinical.patients','clinical.vital_readings','clinical.alarms',
    'clinical.observations','clinical.alarm_thresholds','devices.monitors','public.staff'] loop
    execute format('alter table %s enable row level security', t);
    execute format('alter table %s force row level security', t);
  end loop; end $$;

create policy vitals_select on clinical.vital_readings for select to authenticated
  using (public.has_permission('patient:read') and public.can_access_patient(patient_id));
create policy obs_insert on clinical.observations for insert to authenticated
  with check (public.has_permission('observation:write') and public.can_access_patient(patient_id)
              and author_id = auth.uid());
create policy staff_self on public.staff for select to authenticated
  using (id = auth.uid() or public.has_permission('staff:manage'));

alter role acme_api nobypassrls; alter role acme_simulator nobypassrls;
```

**Implementation Guidance:**
- Enable and FORCE RLS on every table in `supabase/migrations/` (including Realtime-published tables and `storage.objects` policies for report buckets).
- Policies use helper functions (`has_permission`, `can_access_patient`) with `security definer set search_path = ''`; wrap `auth.uid()` as `(select auth.uid())` for performance.
- Supabase Realtime Postgres Changes respect RLS for `authenticated`; verify a nurse only receives events for their ward's patients.
- Review: `select oid, relname, relrowsecurity, relforcerowsecurity from pg_class where relnamespace::regnamespace::text in ('clinical','devices','public','simulation','audit') and relkind = 'r';` and inspect `pg_policies`.
- Confirm no app role has `rolbypassrls` (`\du+`); only `postgres`/`service_role` do, and they are not used by request handlers.
- Reference: SD Elements guidance for T2619.

**Success Criteria:**
- [ ] Every application table has `relrowsecurity` and `relforcerowsecurity` true (pgTAP).
- [ ] Nurse in Ward A gets zero rows / zero Realtime events for Ward B patients.
- [ ] `acme_api`, `acme_simulator`, `authenticated`, `anon` all report `rolbypassrls = false`.

**Status:** Applied
