-- ACME Clinical: authorization hardening (RBAC group roles, permission matrix in SQL, separation of
-- duties, break-glass lifecycle, reset via a dedicated SECURITY DEFINER owner). Idempotent.
--
-- Database accounts (one purpose each; passwords are set out-of-band, never committed):
--   acme_api          LOGIN   request handling by the FastAPI backend. Holds NO direct grants: it only
--                             inherits the privileges of the group role acme_api_rw.
--   acme_api_rw       NOLOGIN group role carrying every table/column/function privilege the API needs.
--                             No DELETE except staff_ward_assignments, no TRUNCATE/REFERENCES/TRIGGER,
--                             no DDL, owns nothing. Audit events are insert-only.
--   acme_reset_owner  NOLOGIN owns only public.reset_simulation_data(); the only holder of DELETE on
--                             readings/alarms/observations, used exclusively through that function.
--   acme_reporting    NOLOGIN read-only aggregates (0002).
--   postgres                  migrations only (CLI/CI); never used by request handlers.
-- Application-level RBAC: public.role_permissions mirrors backend/app/core/security.py PERMISSIONS
-- exactly (a test compares them) and RLS policies call public.has_permission().

-- ---------------------------------------------------------------------------
-- 1. Roles
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'acme_api_rw') then
    create role acme_api_rw nologin nosuperuser nocreatedb nocreaterole nobypassrls noreplication;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'acme_reset_owner') then
    create role acme_reset_owner nologin nosuperuser nocreatedb nocreaterole nobypassrls noreplication;
  end if;
end $$;

alter role acme_api nosuperuser nocreatedb nocreaterole nobypassrls noreplication inherit;
grant usage on schema public to acme_api_rw, acme_reset_owner;

-- Deny by default for objects created later by the migration owner (Supabase grants anon/authenticated
-- everything on new public objects unless told otherwise).
alter default privileges in schema public revoke all on tables from public, anon, authenticated;
alter default privileges in schema public revoke all on sequences from public, anon, authenticated;
alter default privileges in schema public revoke execute on functions from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. Permission matrix (application RBAC) — must equal PERMISSIONS in backend/app/core/security.py
-- ---------------------------------------------------------------------------
create table if not exists public.role_permissions (
  role public.app_role not null,
  permission text not null check (permission ~ '^[a-z_]+:[a-z_]+$'),
  primary key (role, permission)
);
revoke all on public.role_permissions from public, anon, authenticated;

delete from public.role_permissions;
insert into public.role_permissions (role, permission) values
  ('nurse', 'patient:read'), ('nurse', 'observation:write'), ('nurse', 'alarm:read'), ('nurse', 'alarm:ack'),
  ('nurse', 'device:read'), ('nurse', 'file:write'), ('nurse', 'break_glass:request'),
  ('physician', 'patient:read'), ('physician', 'observation:write'), ('physician', 'alarm:read'),
  ('physician', 'alarm:ack'), ('physician', 'threshold:write'), ('physician', 'device:read'),
  ('physician', 'report:read'), ('physician', 'file:write'), ('physician', 'break_glass:request'),
  ('biomed_tech', 'alarm:read'), ('biomed_tech', 'device:read'), ('biomed_tech', 'device:write'),
  ('biomed_tech', 'maintenance:write'),
  ('admin', 'patient:read'), ('admin', 'alarm:read'), ('admin', 'device:read'), ('admin', 'device:write'),
  ('admin', 'report:read'), ('admin', 'staff:manage'), ('admin', 'settings:manage'),
  ('admin', 'simulation:control'), ('admin', 'events:read_all'), ('admin', 'break_glass:review');

create or replace function public.has_permission(p_perm text) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists (select 1 from public.role_permissions rp
                 where rp.role = public.current_staff_role() and rp.permission = p_perm)
$$;
revoke execute on function public.has_permission(text) from public, anon;

-- ---------------------------------------------------------------------------
-- 3. Break-glass lifecycle: early revocation, review outcome, reviewer must differ from requester
-- ---------------------------------------------------------------------------
alter table public.break_glass_grants add column if not exists revoked_at timestamptz;
alter table public.break_glass_grants add column if not exists revoked_by uuid references public.staff_profiles(user_id);
alter table public.break_glass_grants add column if not exists review_outcome text;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'break_glass_reviewer_differs') then
    alter table public.break_glass_grants add constraint break_glass_reviewer_differs
      check (reviewed_by is null or reviewed_by <> user_id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'break_glass_review_outcome') then
    alter table public.break_glass_grants add constraint break_glass_review_outcome
      check ((reviewed_at is null and review_outcome is null)
             or (reviewed_at is not null and review_outcome in ('appropriate', 'inappropriate')));
  end if;
end $$;

-- Patient access: assigned ward, or an unexpired AND unrevoked break-glass grant.
create or replace function public.can_access_patient(p_patient uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select public.current_staff_role() in ('nurse', 'physician', 'admin') and (
      exists (select 1 from public.patients p where p.id = p_patient and public.can_access_ward(p.ward_id))
   or exists (select 1 from public.break_glass_grants g
              where g.patient_id = p_patient and g.user_id = public.current_staff_id()
                and g.revoked_at is null and g.expires_at > now()))
$$;

-- Grant id when the caller reaches this patient ONLY through break-glass (used to audit each action).
create or replace function public.active_break_glass_grant(p_patient uuid) returns uuid
language sql stable security definer set search_path = public, pg_temp as $$
  select g.id from public.break_glass_grants g join public.patients p on p.id = g.patient_id
  where g.patient_id = p_patient and g.user_id = public.current_staff_id()
    and g.revoked_at is null and g.expires_at > now() and not public.can_access_ward(p.ward_id)
  order by g.expires_at desc limit 1
$$;
revoke execute on function public.active_break_glass_grant(uuid) from public, anon, authenticated;

-- Alarm limits may only be changed inside the caller's own ward scope (never under break-glass).
create or replace function public.can_configure_thresholds(p_ward uuid, p_patient uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select public.has_permission('threshold:write') and (
       (p_ward is not null and public.can_access_ward(p_ward))
    or (p_patient is not null and exists (select 1 from public.patients p
                                          where p.id = p_patient and public.can_access_ward(p.ward_id))))
$$;
revoke execute on function public.can_configure_thresholds(uuid, uuid) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 4. Separation of duties for staff administration
-- ---------------------------------------------------------------------------
-- Two-person rule: granting the administrator role requires a request by one administrator and approval
-- (and application) by a different administrator; the target can never approve.
create table if not exists public.staff_role_requests (
  id uuid primary key default gen_random_uuid(),
  target_user_id uuid not null references public.staff_profiles(user_id) on delete cascade,
  new_role public.app_role not null,
  requested_by uuid not null references public.staff_profiles(user_id),
  requested_at timestamptz not null default now(),
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  decided_by uuid references public.staff_profiles(user_id),
  decided_at timestamptz,
  check (requested_by <> target_user_id),
  check (decided_by is null or (decided_by <> requested_by and decided_by <> target_user_id)),
  check ((status = 'pending') = (decided_by is null))
);
revoke all on public.staff_role_requests from public, anon, authenticated;

create or replace function public.staff_profiles_guard() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  actor uuid := public.current_staff_id();
begin
  if actor is null then
    return new;  -- migrations / operator CLI, not an API request
  end if;
  if tg_op = 'INSERT' then
    if new.role = 'admin' then
      raise exception 'new accounts cannot be created as administrators; use the two-person promotion'
        using errcode = '42501';
    end if;
    return new;
  end if;
  if new.user_id = actor and (new.role is distinct from old.role or new.is_active is distinct from old.is_active) then
    raise exception 'staff members cannot change their own role or activation' using errcode = '42501';
  end if;
  if new.role = 'admin' and old.role is distinct from 'admin' and not exists (
      select 1 from public.staff_role_requests r
      where r.target_user_id = new.user_id and r.new_role = 'admin' and r.status = 'approved'
        and r.decided_by = actor and r.decided_at > now() - interval '1 hour') then
    raise exception 'granting the administrator role requires approval by a second administrator'
      using errcode = '42501';
  end if;
  return new;
end $$;
revoke execute on function public.staff_profiles_guard() from public, anon, authenticated;
drop trigger if exists staff_profiles_guard_upd on public.staff_profiles;
create trigger staff_profiles_guard_upd before update of role, is_active on public.staff_profiles
  for each row execute function public.staff_profiles_guard();
drop trigger if exists staff_profiles_guard_ins on public.staff_profiles;
create trigger staff_profiles_guard_ins before insert on public.staff_profiles
  for each row execute function public.staff_profiles_guard();

-- ---------------------------------------------------------------------------
-- 5. Demo reset: the only bulk-delete path, owned by a dedicated non-login role
-- ---------------------------------------------------------------------------
create or replace function public.reset_simulation_data() returns void
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if not public.has_permission('simulation:control') then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  delete from public.readings;
  delete from public.alarms;
  delete from public.observations;
end $$;
revoke execute on function public.reset_simulation_data() from public, anon, authenticated;

grant select, delete on public.readings, public.alarms, public.observations to acme_reset_owner;
grant execute on function public.has_permission(text), public.current_staff_role(), public.current_staff_id()
  to acme_reset_owner;
do $$
begin
  alter function public.reset_simulation_data() owner to acme_reset_owner;
exception when insufficient_privilege then
  -- Hosted projects where the migration role cannot SET ROLE to acme_reset_owner keep the migration
  -- owner; the permission check inside the function still applies.
  raise notice 'reset_simulation_data() stays owned by %', current_user;
end $$;

-- ---------------------------------------------------------------------------
-- 6. RBAC grants: everything to the group role, nothing directly to the login role
-- ---------------------------------------------------------------------------
grant select on public.wards, public.beds, public.patients, public.observations, public.monitor_assignments,
  public.maintenance_records, public.readings, public.alarm_thresholds, public.alarms, public.attachments,
  public.break_glass_grants, public.simulation_state, public.security_settings, public.staff_profiles,
  public.staff_ward_assignments, public.events, public.role_permissions, public.staff_role_requests to acme_api_rw;
grant select (id, serial, model, firmware_version, status, battery_pct, last_heartbeat_at, created_at)
  on public.monitors to acme_api_rw;

grant update (full_name, role, is_active, deactivated_at, last_login_at, previous_login_at, previous_login_ip,
  privacy_notice_accepted_at) on public.staff_profiles to acme_api_rw;
grant insert on public.staff_profiles, public.staff_ward_assignments to acme_api_rw;
grant delete on public.staff_ward_assignments to acme_api_rw;  -- ward re-assignment only
grant insert on public.staff_role_requests to acme_api_rw;
grant update (status, decided_by, decided_at) on public.staff_role_requests to acme_api_rw;
grant update (bed_id, discharged_at, retention_until) on public.patients to acme_api_rw;
grant insert on public.observations to acme_api_rw;
grant update (status, battery_pct, last_heartbeat_at, firmware_version) on public.monitors to acme_api_rw;
grant insert on public.monitor_assignments to acme_api_rw;
grant update (unassigned_at) on public.monitor_assignments to acme_api_rw;
grant insert on public.maintenance_records to acme_api_rw;
grant insert on public.readings to acme_api_rw;
grant usage on sequence public.readings_id_seq to acme_api_rw;
grant insert on public.alarm_thresholds to acme_api_rw;
grant update (low_limit, high_limit, updated_by, updated_at) on public.alarm_thresholds to acme_api_rw;
grant insert on public.alarms to acme_api_rw;
grant update (state, last_seen_at, resolved_at, acknowledged_at, acknowledged_by, ack_note) on public.alarms to acme_api_rw;
grant insert on public.attachments to acme_api_rw;
grant insert on public.break_glass_grants to acme_api_rw;
grant update (reviewed_by, reviewed_at, review_outcome, revoked_at, revoked_by) on public.break_glass_grants to acme_api_rw;
grant update (scenario, monitor_scenarios, tick, version, updated_at, updated_by) on public.simulation_state to acme_api_rw;
grant update (password_min_length, session_idle_minutes, session_absolute_hours, max_concurrent_sessions,
  lockout_threshold, lockout_minutes, require_mfa_for_admin, data_retention_days, updated_by)
  on public.security_settings to acme_api_rw;
grant insert on public.events to acme_api_rw;              -- append only: no update/delete/truncate
grant usage on sequence public.events_id_seq to acme_api_rw;

grant execute on function public.current_staff_id(), public.current_staff_role(), public.can_access_ward(uuid),
  public.can_access_patient(uuid), public.verify_event_chain(), public.staff_identity(uuid),
  public.patient_exists(uuid), public.has_permission(text), public.active_break_glass_grant(uuid),
  public.can_configure_thresholds(uuid, uuid), public.reset_simulation_data() to acme_api_rw;
grant execute on function public.has_permission(text) to authenticated;

grant acme_api_rw to acme_api;

-- Remove every direct privilege from the login role (column privileges go with the table revoke).
revoke all on all tables in schema public from acme_api;
revoke all on all sequences in schema public from acme_api;
revoke execute on all functions in schema public from acme_api;

-- Re-assert default deny for anonymous browser sessions on every table, sequence and function.
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;
revoke execute on all functions in schema public from anon;

-- ---------------------------------------------------------------------------
-- 7. Row-level security: enabled and forced on the new tables; policies use shared helpers
-- ---------------------------------------------------------------------------
alter table public.role_permissions enable row level security;
alter table public.role_permissions force row level security;
alter table public.staff_role_requests enable row level security;
alter table public.staff_role_requests force row level security;

drop policy if exists role_permissions_read on public.role_permissions;
create policy role_permissions_read on public.role_permissions for select to acme_api_rw
  using (public.current_staff_role() is not null);

drop policy if exists role_requests_read on public.staff_role_requests;
create policy role_requests_read on public.staff_role_requests for select to acme_api_rw
  using (public.has_permission('staff:manage'));
drop policy if exists role_requests_insert on public.staff_role_requests;
create policy role_requests_insert on public.staff_role_requests for insert to acme_api_rw
  with check (public.has_permission('staff:manage') and requested_by = public.current_staff_id()
              and status = 'pending');
drop policy if exists role_requests_decide on public.staff_role_requests;
create policy role_requests_decide on public.staff_role_requests for update to acme_api_rw
  using (public.has_permission('staff:manage') and status = 'pending'
         and requested_by <> public.current_staff_id() and target_user_id <> public.current_staff_id())
  with check (decided_by = public.current_staff_id());

-- Alarm limits: physicians (threshold:write) within their own wards only; administrators no longer.
drop policy if exists thresholds_write on public.alarm_thresholds;
create policy thresholds_write on public.alarm_thresholds for all to acme_api
  using (public.can_configure_thresholds(ward_id, patient_id))
  with check (public.can_configure_thresholds(ward_id, patient_id));

-- Break glass: request own grant; revoke own grant early; reviewers handle other users' grants only.
drop policy if exists bg_insert on public.break_glass_grants;
create policy bg_insert on public.break_glass_grants for insert to acme_api
  with check (public.has_permission('break_glass:request') and user_id = public.current_staff_id()
              and revoked_at is null and reviewed_at is null);
drop policy if exists bg_review on public.break_glass_grants;
create policy bg_review on public.break_glass_grants for update to acme_api
  using (public.has_permission('break_glass:review') and user_id <> public.current_staff_id())
  with check (public.has_permission('break_glass:review') and user_id <> public.current_staff_id());
drop policy if exists bg_self_revoke on public.break_glass_grants;
create policy bg_self_revoke on public.break_glass_grants for update to acme_api
  using (user_id = public.current_staff_id() and reviewed_at is null)
  with check (user_id = public.current_staff_id() and reviewed_at is null and revoked_by = public.current_staff_id());

-- Bulk deletes happen only inside reset_simulation_data() (as acme_reset_owner).
drop policy if exists observations_reset on public.observations;
drop policy if exists alarms_reset on public.alarms;
drop policy if exists readings_write on public.readings;
create policy readings_insert on public.readings for insert to acme_api
  with check (public.current_staff_role() is not null);
drop policy if exists reset_owner_readings on public.readings;
create policy reset_owner_readings on public.readings for all to acme_reset_owner using (true) with check (false);
drop policy if exists reset_owner_alarms on public.alarms;
create policy reset_owner_alarms on public.alarms for all to acme_reset_owner using (true) with check (false);
drop policy if exists reset_owner_observations on public.observations;
create policy reset_owner_observations on public.observations for all to acme_reset_owner using (true) with check (false);

-- Privileged administration policies expressed through the shared permission helper.
drop policy if exists staff_insert on public.staff_profiles;
create policy staff_insert on public.staff_profiles for insert to acme_api
  with check (public.has_permission('staff:manage'));
drop policy if exists staff_update on public.staff_profiles;
create policy staff_update on public.staff_profiles for update to acme_api
  using (user_id = public.current_staff_id() or public.has_permission('staff:manage'))
  with check (user_id = public.current_staff_id() or public.has_permission('staff:manage'));
drop policy if exists staff_wards_write on public.staff_ward_assignments;
create policy staff_wards_write on public.staff_ward_assignments for all to acme_api
  using (public.has_permission('staff:manage')) with check (public.has_permission('staff:manage'));
drop policy if exists sim_write on public.simulation_state;
create policy sim_write on public.simulation_state for update to acme_api
  using (public.has_permission('simulation:control')) with check (public.has_permission('simulation:control'));
drop policy if exists settings_write on public.security_settings;
create policy settings_write on public.security_settings for update to acme_api
  using (public.has_permission('settings:manage')) with check (public.has_permission('settings:manage'));
drop policy if exists monitors_update on public.monitors;
create policy monitors_update on public.monitors for update to acme_api
  using (public.has_permission('device:write')) with check (public.has_permission('device:write'));
drop policy if exists assignments_write on public.monitor_assignments;
create policy assignments_write on public.monitor_assignments for all to acme_api
  using (public.has_permission('device:write')) with check (public.has_permission('device:write'));
drop policy if exists maintenance_write on public.maintenance_records;
create policy maintenance_write on public.maintenance_records for all to acme_api
  using (public.has_permission('maintenance:write')) with check (public.has_permission('maintenance:write'));
drop policy if exists observations_insert on public.observations;
create policy observations_insert on public.observations for insert to acme_api
  with check (public.has_permission('observation:write') and author_id = public.current_staff_id()
              and public.can_access_patient(patient_id));
drop policy if exists attachments_insert on public.attachments;
create policy attachments_insert on public.attachments for insert to acme_api
  with check (public.has_permission('file:write') and uploaded_by = public.current_staff_id()
              and public.can_access_patient(patient_id));
