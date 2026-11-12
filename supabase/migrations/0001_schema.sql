-- ACME Clinical: core schema.
-- Simulated ward patient monitoring. Demo patients are fictitious, but the schema is designed
-- as if it held real health data: RLS on every table, least-privilege API role, append-only audit.

create extension if not exists pgcrypto;
create extension if not exists citext;

-- ---------------------------------------------------------------------------
-- Enumerations
-- ---------------------------------------------------------------------------
create type public.app_role as enum ('nurse', 'physician', 'biomed_tech', 'admin');
create type public.monitor_status as enum ('online', 'offline', 'maintenance', 'retired');
create type public.vital_parameter as enum ('heart_rate', 'spo2', 'resp_rate', 'bp_systolic', 'bp_diastolic');
create type public.alarm_type as enum (
  'low_heart_rate', 'high_heart_rate', 'low_spo2', 'low_resp_rate', 'high_resp_rate',
  'low_bp_systolic', 'high_bp_systolic', 'low_battery', 'sensor_fault', 'connection_lost'
);
create type public.alarm_priority as enum ('high', 'medium', 'low');
create type public.alarm_state as enum ('active', 'resolved');
create type public.reading_quality as enum ('good', 'degraded', 'invalid');
create type public.sim_scenario as enum ('normal', 'low_saturation', 'low_battery', 'sensor_fault', 'connection_loss');

-- ---------------------------------------------------------------------------
-- Organisation
-- ---------------------------------------------------------------------------
create table public.wards (
  id uuid primary key default gen_random_uuid(),
  code text not null unique check (code ~ '^[A-Z0-9-]{2,16}$'),
  name text not null check (char_length(name) between 1 and 80),
  created_at timestamptz not null default now()
);

create table public.beds (
  id uuid primary key default gen_random_uuid(),
  ward_id uuid not null references public.wards(id) on delete restrict,
  label text not null check (char_length(label) between 1 and 16),
  unique (ward_id, label)
);

-- One row per Supabase Auth user. Role and activation are managed only by administrators via the API.
create table public.staff_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email citext not null unique,
  full_name text not null check (char_length(full_name) between 1 and 120),
  role public.app_role not null,
  is_active boolean not null default true,
  last_login_at timestamptz,
  previous_login_at timestamptz,
  previous_login_ip inet,
  privacy_notice_accepted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deactivated_at timestamptz
);

create table public.staff_ward_assignments (
  user_id uuid not null references public.staff_profiles(user_id) on delete cascade,
  ward_id uuid not null references public.wards(id) on delete cascade,
  primary key (user_id, ward_id)
);

-- ---------------------------------------------------------------------------
-- Patients (fictitious demo data; pseudonymous code is the primary identifier shown in lists)
-- ---------------------------------------------------------------------------
create table public.patients (
  id uuid primary key default gen_random_uuid(),
  pseudonym text not null unique check (pseudonym ~ '^PT-[0-9]{4}$'),
  display_name text not null check (char_length(display_name) between 1 and 120),
  birth_year smallint check (birth_year between 1900 and 2100),
  ward_id uuid not null references public.wards(id) on delete restrict,
  bed_id uuid unique references public.beds(id) on delete set null,
  admitted_at timestamptz not null default now(),
  discharged_at timestamptz,
  retention_until date
);

create table public.observations (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.patients(id) on delete cascade,
  author_id uuid not null references public.staff_profiles(user_id) on delete restrict,
  body text not null check (char_length(body) between 1 and 2000),
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Devices
-- ---------------------------------------------------------------------------
create table public.monitors (
  id uuid primary key default gen_random_uuid(),
  serial text not null unique check (serial ~ '^MON-[0-9]{4}$'),
  model text not null check (char_length(model) between 1 and 60),
  firmware_version text not null default '1.0.0',
  -- SHA-256 of the per-device secret (simulated device authenticity, never stored in clear).
  device_secret_hash bytea not null,
  status public.monitor_status not null default 'online',
  battery_pct smallint not null default 100 check (battery_pct between 0 and 100),
  last_heartbeat_at timestamptz,
  created_at timestamptz not null default now()
);

create table public.monitor_assignments (
  id uuid primary key default gen_random_uuid(),
  monitor_id uuid not null references public.monitors(id) on delete restrict,
  bed_id uuid not null references public.beds(id) on delete restrict,
  assigned_by uuid not null references public.staff_profiles(user_id),
  assigned_at timestamptz not null default now(),
  unassigned_at timestamptz,
  check (unassigned_at is null or unassigned_at >= assigned_at)
);
create unique index monitor_assignments_active_monitor on public.monitor_assignments(monitor_id) where unassigned_at is null;
create unique index monitor_assignments_active_bed on public.monitor_assignments(bed_id) where unassigned_at is null;

create table public.maintenance_records (
  id uuid primary key default gen_random_uuid(),
  monitor_id uuid not null references public.monitors(id) on delete restrict,
  kind text not null check (kind in ('inspection', 'calibration', 'battery_replacement', 'repair', 'firmware_update')),
  notes text not null default '' check (char_length(notes) <= 1000),
  performed_by uuid not null references public.staff_profiles(user_id),
  performed_at timestamptz not null default now(),
  next_due date
);

-- ---------------------------------------------------------------------------
-- Readings, thresholds, alarms
-- ---------------------------------------------------------------------------
create table public.readings (
  id bigserial primary key,
  monitor_id uuid not null references public.monitors(id) on delete restrict,
  patient_id uuid references public.patients(id) on delete cascade,
  recorded_at timestamptz not null default now(),
  heart_rate smallint check (heart_rate between 0 and 300),
  spo2 smallint check (spo2 between 0 and 100),
  resp_rate smallint check (resp_rate between 0 and 80),
  bp_systolic smallint check (bp_systolic between 0 and 300),
  bp_diastolic smallint check (bp_diastolic between 0 and 200),
  ecg real[] check (ecg is null or cardinality(ecg) <= 500),
  quality public.reading_quality not null default 'good'
);
create index readings_patient_time on public.readings(patient_id, recorded_at desc);

-- Thresholds are per ward (default) with optional per-patient override.
create table public.alarm_thresholds (
  id uuid primary key default gen_random_uuid(),
  ward_id uuid references public.wards(id) on delete cascade,
  patient_id uuid references public.patients(id) on delete cascade,
  parameter public.vital_parameter not null,
  low_limit smallint not null,
  high_limit smallint not null,
  updated_by uuid references public.staff_profiles(user_id),
  updated_at timestamptz not null default now(),
  check ((ward_id is null) <> (patient_id is null)),
  check (low_limit >= 0 and high_limit <= 300 and low_limit < high_limit)
);
create unique index alarm_thresholds_ward_param on public.alarm_thresholds(ward_id, parameter) where patient_id is null;
create unique index alarm_thresholds_patient_param on public.alarm_thresholds(patient_id, parameter) where ward_id is null;

create table public.alarms (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid references public.patients(id) on delete cascade,
  monitor_id uuid not null references public.monitors(id) on delete restrict,
  type public.alarm_type not null,
  priority public.alarm_priority not null,
  state public.alarm_state not null default 'active',
  message text not null check (char_length(message) <= 200),
  raised_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  resolved_at timestamptz,
  -- Acknowledgement is independent of resolution: an acknowledged alarm stays active while the condition persists.
  acknowledged_at timestamptz,
  acknowledged_by uuid references public.staff_profiles(user_id),
  ack_note text check (ack_note is null or char_length(ack_note) <= 500),
  check (state = 'active' or resolved_at is not null)
);
create unique index alarms_one_active_per_condition on public.alarms(monitor_id, type) where state = 'active';
create index alarms_state_priority on public.alarms(state, priority, raised_at desc);

-- ---------------------------------------------------------------------------
-- Files (Supabase Storage metadata; objects live in the private 'clinical-files' bucket)
-- ---------------------------------------------------------------------------
create table public.attachments (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.patients(id) on delete cascade,
  object_path text not null unique check (object_path ~ '^patients/[0-9a-f-]{36}/[0-9a-f-]{36}\.(pdf|png|jpg)$'),
  original_name text not null check (char_length(original_name) <= 120),
  content_type text not null check (content_type in ('application/pdf', 'image/png', 'image/jpeg')),
  size_bytes integer not null check (size_bytes between 1 and 5242880),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  uploaded_by uuid not null references public.staff_profiles(user_id),
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Emergency access ("break glass"), simulation state, security settings
-- ---------------------------------------------------------------------------
create table public.break_glass_grants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.staff_profiles(user_id),
  patient_id uuid not null references public.patients(id) on delete cascade,
  reason text not null check (char_length(reason) between 10 and 500),
  granted_at timestamptz not null default now(),
  expires_at timestamptz not null,
  reviewed_by uuid references public.staff_profiles(user_id),
  reviewed_at timestamptz,
  check (expires_at > granted_at and expires_at <= granted_at + interval '4 hours')
);

create table public.simulation_state (
  id smallint primary key default 1 check (id = 1),
  scenario public.sim_scenario not null default 'normal',
  -- optional per-monitor overrides: {"<monitor uuid>": "<scenario>"}
  monitor_scenarios jsonb not null default '{}'::jsonb check (jsonb_typeof(monitor_scenarios) = 'object'),
  tick bigint not null default 0,
  version bigint not null default 0,
  updated_at timestamptz not null default now(),
  updated_by uuid references public.staff_profiles(user_id)
);

-- Unified, administrator-managed security settings (single row).
create table public.security_settings (
  id smallint primary key default 1 check (id = 1),
  password_min_length smallint not null default 12 check (password_min_length between 12 and 128),
  session_idle_minutes smallint not null default 15 check (session_idle_minutes between 5 and 60),
  session_absolute_hours smallint not null default 12 check (session_absolute_hours between 1 and 24),
  max_concurrent_sessions smallint not null default 2 check (max_concurrent_sessions between 1 and 10),
  lockout_threshold smallint not null default 5 check (lockout_threshold between 3 and 10),
  lockout_minutes smallint not null default 15 check (lockout_minutes between 5 and 120),
  require_mfa_for_admin boolean not null default true,
  data_retention_days integer not null default 365 check (data_retention_days between 30 and 3650),
  updated_by uuid references public.staff_profiles(user_id),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Append-only, hash-chained audit/event log
-- ---------------------------------------------------------------------------
create table public.events (
  id bigserial primary key,
  occurred_at timestamptz not null default clock_timestamp(),
  actor_id uuid,
  actor_role public.app_role,
  action text not null check (action ~ '^[a-z_]+\.[a-z_]+$'),
  entity_type text not null check (char_length(entity_type) <= 40),
  entity_id text check (entity_id is null or char_length(entity_id) <= 64),
  outcome text not null default 'success' check (outcome in ('success', 'denied', 'failure')),
  request_id text check (request_id is null or char_length(request_id) <= 64),
  details jsonb not null default '{}'::jsonb check (pg_column_size(details) <= 4096),
  prev_hash text,
  hash text not null default ''
);
create index events_time on public.events(occurred_at desc);
create index events_entity on public.events(entity_type, entity_id);

create or replace function public.events_hash_chain() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  last_hash text;
begin
  perform pg_advisory_xact_lock(hashtext('public.events'));
  select e.hash into last_hash from public.events e order by e.id desc limit 1;
  new.prev_hash := coalesce(last_hash, repeat('0', 64));
  new.occurred_at := clock_timestamp();
  new.hash := encode(digest(
    new.prev_hash || '|' || new.occurred_at::text || '|' || coalesce(new.actor_id::text, '') || '|' ||
    new.action || '|' || new.entity_type || '|' || coalesce(new.entity_id, '') || '|' ||
    new.outcome || '|' || new.details::text, 'sha256'), 'hex');
  return new;
end $$;

create trigger events_hash_chain before insert on public.events
  for each row execute function public.events_hash_chain();

create or replace function public.events_block_mutation() returns trigger
language plpgsql as $$
begin
  raise exception 'events are append-only';
end $$;

create trigger events_no_update before update or delete on public.events
  for each row execute function public.events_block_mutation();
create trigger events_no_truncate before truncate on public.events
  for each statement execute function public.events_block_mutation();

-- Verify the chain; returns the first broken id, or null when intact.
create or replace function public.verify_event_chain() returns bigint
language plpgsql stable security definer set search_path = public, pg_temp as $$
declare
  r record;
  expected_prev text := repeat('0', 64);
begin
  for r in select * from public.events order by id loop
    if r.prev_hash is distinct from expected_prev or r.hash <> encode(digest(
      r.prev_hash || '|' || r.occurred_at::text || '|' || coalesce(r.actor_id::text, '') || '|' ||
      r.action || '|' || r.entity_type || '|' || coalesce(r.entity_id, '') || '|' ||
      r.outcome || '|' || r.details::text, 'sha256'), 'hex') then
      return r.id;
    end if;
    expected_prev := r.hash;
  end loop;
  return null;
end $$;

-- updated_at maintenance
create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at := now(); return new; end $$;
create trigger staff_profiles_touch before update on public.staff_profiles for each row execute function public.touch_updated_at();
create trigger security_settings_touch before update on public.security_settings for each row execute function public.touch_updated_at();
