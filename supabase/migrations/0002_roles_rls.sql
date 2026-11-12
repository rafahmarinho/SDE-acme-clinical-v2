-- ACME Clinical: least-privilege database roles, RBAC grants and row-level security.
--
-- Roles
--   acme_api       login role used ONLY by the FastAPI backend (password set out-of-band, never in git).
--                  The API verifies the Supabase JWT, then sets app.user_id / app.role for the transaction.
--   authenticated  Supabase browser sessions: read-only access needed for Realtime subscriptions.
--   anon           no access to any application table.
-- No application code uses the postgres superuser or the service_role key for data access.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'acme_api') then
    create role acme_api login noinherit nocreatedb nocreaterole nosuperuser nobypassrls connection limit 20;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'acme_reporting') then
    -- group role for read-only reporting/analytics consumers (RBAC instead of individual accounts)
    create role acme_reporting nologin;
  end if;
end $$;

alter role acme_api set statement_timeout = '10s';
alter role acme_api set idle_in_transaction_session_timeout = '15s';
alter role acme_api set search_path = public, pg_temp;

revoke all on schema public from public;
grant usage on schema public to acme_api, authenticated, acme_reporting;
revoke all on all tables in schema public from anon, authenticated, acme_api, acme_reporting;
revoke all on all sequences in schema public from anon, authenticated;
revoke execute on all functions in schema public from public, anon;

-- ---------------------------------------------------------------------------
-- Identity helpers. app.* settings are honoured only for the acme_api role, so a browser
-- session can never spoof them; browser sessions resolve identity from auth.uid().
-- ---------------------------------------------------------------------------
create or replace function public.current_staff_id() returns uuid
language sql stable security definer set search_path = public, pg_temp as $$
  select case
    when session_user = 'acme_api' then nullif(current_setting('app.user_id', true), '')::uuid
    else auth.uid()
  end
$$;

create or replace function public.current_staff_role() returns public.app_role
language sql stable security definer set search_path = public, pg_temp as $$
  select case
    when session_user = 'acme_api' then nullif(current_setting('app.role', true), '')::public.app_role
    else (select sp.role from public.staff_profiles sp where sp.user_id = auth.uid() and sp.is_active)
  end
$$;

create or replace function public.can_access_ward(p_ward uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select public.current_staff_role() = 'admin'
      or exists (select 1 from public.staff_ward_assignments a
                 where a.user_id = public.current_staff_id() and a.ward_id = p_ward)
$$;

-- Patient access: assigned ward, or an unexpired break-glass grant. Biomedical technicians
-- work with devices, not patient records.
create or replace function public.can_access_patient(p_patient uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select public.current_staff_role() in ('nurse', 'physician', 'admin') and (
      exists (select 1 from public.patients p where p.id = p_patient and public.can_access_ward(p.ward_id))
   or exists (select 1 from public.break_glass_grants g
              where g.patient_id = p_patient and g.user_id = public.current_staff_id() and g.expires_at > now()))
$$;

-- Bootstrap lookup used by the API right after JWT verification (before app.role is known).
create or replace function public.staff_identity(p_user uuid)
returns table (user_id uuid, email citext, role public.app_role, is_active boolean,
               session_idle_minutes smallint, session_absolute_hours smallint,
               max_concurrent_sessions smallint, require_mfa_for_admin boolean)
language sql stable security definer set search_path = public, pg_temp as $$
  select sp.user_id, sp.email, sp.role, sp.is_active, s.session_idle_minutes, s.session_absolute_hours,
         s.max_concurrent_sessions, s.require_mfa_for_admin
  from public.staff_profiles sp cross join public.security_settings s
  where sp.user_id = p_user
$$;
revoke execute on function public.staff_identity(uuid) from public, anon, authenticated;
grant execute on function public.staff_identity(uuid) to acme_api;

-- Break-glass needs to confirm a patient exists even when RLS hides it from the caller.
create or replace function public.patient_exists(p_patient uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists (select 1 from public.patients where id = p_patient and discharged_at is null)
$$;
revoke execute on function public.patient_exists(uuid) from public, anon, authenticated;
grant execute on function public.patient_exists(uuid) to acme_api;

grant execute on function public.current_staff_id(), public.current_staff_role(),
  public.can_access_ward(uuid), public.can_access_patient(uuid) to acme_api, authenticated;
grant execute on function public.verify_event_chain() to acme_api;

-- ---------------------------------------------------------------------------
-- Table privileges (column-level where it matters)
-- ---------------------------------------------------------------------------
grant select on public.wards, public.beds, public.patients, public.observations, public.monitor_assignments,
  public.maintenance_records, public.readings, public.alarm_thresholds, public.alarms, public.attachments,
  public.break_glass_grants, public.simulation_state, public.security_settings, public.staff_profiles,
  public.staff_ward_assignments, public.events to acme_api;
grant select (id, serial, model, firmware_version, status, battery_pct, last_heartbeat_at, created_at)
  on public.monitors to acme_api;

grant update (full_name, role, is_active, deactivated_at, last_login_at, previous_login_at, previous_login_ip,
  privacy_notice_accepted_at) on public.staff_profiles to acme_api;
grant insert on public.staff_profiles, public.staff_ward_assignments to acme_api;
grant delete on public.staff_ward_assignments to acme_api;
grant update (bed_id, discharged_at, retention_until) on public.patients to acme_api;
grant insert, delete on public.observations to acme_api;
grant update (status, battery_pct, last_heartbeat_at, firmware_version) on public.monitors to acme_api;
grant insert, delete on public.monitor_assignments to acme_api;
grant update (unassigned_at) on public.monitor_assignments to acme_api;
grant insert, delete on public.maintenance_records to acme_api;
grant insert, delete on public.readings to acme_api;
grant usage on sequence public.readings_id_seq to acme_api;
grant insert on public.alarm_thresholds to acme_api;
grant update (low_limit, high_limit, updated_by, updated_at) on public.alarm_thresholds to acme_api;
grant insert, delete on public.alarms to acme_api;
grant update (state, last_seen_at, resolved_at, acknowledged_at, acknowledged_by, ack_note) on public.alarms to acme_api;
grant insert on public.attachments to acme_api;
grant insert on public.break_glass_grants to acme_api;
grant update (reviewed_by, reviewed_at) on public.break_glass_grants to acme_api;
grant update (scenario, monitor_scenarios, tick, version, updated_at, updated_by) on public.simulation_state to acme_api;
grant update (password_min_length, session_idle_minutes, session_absolute_hours, max_concurrent_sessions,
  lockout_threshold, lockout_minutes, require_mfa_for_admin, data_retention_days, updated_by) on public.security_settings to acme_api;
grant insert on public.events to acme_api;              -- append only: no update/delete/truncate
grant usage on sequence public.events_id_seq to acme_api;

-- Browser sessions: read-only, only what Realtime dashboards need.
grant select on public.wards, public.beds, public.alarms, public.monitor_assignments to authenticated;
grant select (id, patient_id, monitor_id, recorded_at, heart_rate, spo2, resp_rate, bp_systolic, bp_diastolic, ecg, quality)
  on public.readings to authenticated;
grant select (id, serial, model, status, battery_pct, last_heartbeat_at) on public.monitors to authenticated;

-- Reporting role: aggregate, pseudonymous data only.
grant select on public.wards, public.alarms, public.readings to acme_reporting;

-- ---------------------------------------------------------------------------
-- Row-level security: enabled and forced on every table.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['wards','beds','staff_profiles','staff_ward_assignments','patients','observations',
    'monitors','monitor_assignments','maintenance_records','readings','alarm_thresholds','alarms','attachments',
    'break_glass_grants','simulation_state','security_settings','events'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
  end loop;
end $$;

-- Reference data
create policy wards_read on public.wards for select to acme_api, authenticated, acme_reporting
  using (public.current_staff_role() is not null or current_user = 'acme_reporting');
create policy beds_read on public.beds for select to acme_api, authenticated
  using (public.current_staff_role() is not null);

-- Staff profiles: self or admin; only admins create/modify other accounts.
create policy staff_read on public.staff_profiles for select to acme_api
  using (user_id = public.current_staff_id() or public.current_staff_role() = 'admin');
create policy staff_insert on public.staff_profiles for insert to acme_api
  with check (public.current_staff_role() = 'admin');
create policy staff_update on public.staff_profiles for update to acme_api
  using (user_id = public.current_staff_id() or public.current_staff_role() = 'admin')
  with check (user_id = public.current_staff_id() or public.current_staff_role() = 'admin');
create policy staff_wards_read on public.staff_ward_assignments for select to acme_api
  using (user_id = public.current_staff_id() or public.current_staff_role() = 'admin');
create policy staff_wards_write on public.staff_ward_assignments for all to acme_api
  using (public.current_staff_role() = 'admin') with check (public.current_staff_role() = 'admin');

-- Patients and clinical records
create policy patients_read on public.patients for select to acme_api
  using (public.can_access_patient(id) or (public.current_staff_role() = 'biomed_tech'));
create policy patients_update on public.patients for update to acme_api
  using (public.can_access_patient(id) or public.current_staff_role() in ('biomed_tech', 'admin'))
  with check (public.can_access_patient(id) or public.current_staff_role() in ('biomed_tech', 'admin'));
create policy observations_read on public.observations for select to acme_api
  using (public.can_access_patient(patient_id));
create policy observations_insert on public.observations for insert to acme_api
  with check (public.current_staff_role() in ('nurse', 'physician') and author_id = public.current_staff_id()
              and public.can_access_patient(patient_id));
create policy observations_reset on public.observations for delete to acme_api
  using (public.current_staff_role() = 'admin');

-- Devices
create policy monitors_read on public.monitors for select to acme_api, authenticated
  using (public.current_staff_role() is not null);
create policy monitors_update on public.monitors for update to acme_api
  using (public.current_staff_role() in ('biomed_tech', 'admin'))
  with check (public.current_staff_role() in ('biomed_tech', 'admin'));
create policy assignments_read on public.monitor_assignments for select to acme_api, authenticated
  using (public.current_staff_role() is not null);
create policy assignments_write on public.monitor_assignments for all to acme_api
  using (public.current_staff_role() in ('biomed_tech', 'admin'))
  with check (public.current_staff_role() in ('biomed_tech', 'admin'));
create policy maintenance_read on public.maintenance_records for select to acme_api
  using (public.current_staff_role() in ('biomed_tech', 'admin'));
create policy maintenance_write on public.maintenance_records for all to acme_api
  using (public.current_staff_role() in ('biomed_tech', 'admin'))
  with check (public.current_staff_role() in ('biomed_tech', 'admin'));

-- Readings / alarms (simulation engine writes run as the acting admin/clinician or the simulation actor)
create policy readings_read on public.readings for select to acme_api, authenticated
  using (patient_id is null or public.can_access_patient(patient_id) or public.current_staff_role() = 'biomed_tech');
create policy readings_reporting on public.readings for select to acme_reporting using (true);
create policy readings_write on public.readings for all to acme_api
  using (public.current_staff_role() = 'admin') with check (public.current_staff_role() is not null);
create policy alarms_read on public.alarms for select to acme_api, authenticated
  using (patient_id is null or public.can_access_patient(patient_id) or public.current_staff_role() = 'biomed_tech');
create policy alarms_reporting on public.alarms for select to acme_reporting using (true);
create policy alarms_insert on public.alarms for insert to acme_api
  with check (public.current_staff_role() is not null);
create policy alarms_update on public.alarms for update to acme_api
  using (public.current_staff_role() is not null) with check (public.current_staff_role() is not null);
create policy alarms_reset on public.alarms for delete to acme_api
  using (public.current_staff_role() = 'admin');

create policy thresholds_read on public.alarm_thresholds for select to acme_api
  using (public.current_staff_role() is not null);
create policy thresholds_write on public.alarm_thresholds for all to acme_api
  using (public.current_staff_role() in ('physician', 'admin'))
  with check (public.current_staff_role() in ('physician', 'admin'));

-- Files
create policy attachments_read on public.attachments for select to acme_api
  using (public.can_access_patient(patient_id));
create policy attachments_insert on public.attachments for insert to acme_api
  with check (public.current_staff_role() in ('nurse', 'physician') and uploaded_by = public.current_staff_id()
              and public.can_access_patient(patient_id));

-- Break glass: users create their own grant; admins review.
create policy bg_read on public.break_glass_grants for select to acme_api
  using (user_id = public.current_staff_id() or public.current_staff_role() = 'admin');
create policy bg_insert on public.break_glass_grants for insert to acme_api
  with check (user_id = public.current_staff_id() and public.current_staff_role() in ('nurse', 'physician'));
create policy bg_review on public.break_glass_grants for update to acme_api
  using (public.current_staff_role() = 'admin' and user_id <> public.current_staff_id())
  with check (public.current_staff_role() = 'admin');

-- Simulation & settings
create policy sim_read on public.simulation_state for select to acme_api using (public.current_staff_role() is not null);
create policy sim_write on public.simulation_state for update to acme_api
  using (public.current_staff_role() = 'admin') with check (public.current_staff_role() = 'admin');
create policy settings_read on public.security_settings for select to acme_api using (public.current_staff_role() is not null);
create policy settings_write on public.security_settings for update to acme_api
  using (public.current_staff_role() = 'admin') with check (public.current_staff_role() = 'admin');

-- Events: everyone appends as themselves; admins read everything, others read their own.
create policy events_insert on public.events for insert to acme_api
  with check (actor_id is null or actor_id = public.current_staff_id());
create policy events_read on public.events for select to acme_api
  using (public.current_staff_role() = 'admin' or actor_id = public.current_staff_id());

-- ---------------------------------------------------------------------------
-- Realtime publication (read-only feeds for dashboards)
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.readings, public.alarms, public.monitors;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Storage: private bucket; objects are only accessed through short-lived signed URLs issued by the API.
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('clinical-files', 'clinical-files', false, 5242880, array['application/pdf', 'image/png', 'image/jpeg'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
-- No storage.objects policies are granted to anon/authenticated: browsers cannot list, read or write the bucket directly.
