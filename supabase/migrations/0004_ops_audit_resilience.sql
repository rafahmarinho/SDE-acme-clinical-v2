-- ACME Clinical: audit non-repudiation, admin alerts, configuration integrity, watchdog.
-- Idempotent. Owned by the logging/files/clinical-safety workstream.

-- ---------------------------------------------------------------------------
-- 1. Audit records: who/where/how + ECDSA signature (T71, T485). Still append-only (T350).
-- ---------------------------------------------------------------------------
alter table public.events add column if not exists source_ip text check (source_ip is null or char_length(source_ip) <= 45);
alter table public.events add column if not exists session_id text check (session_id is null or char_length(session_id) <= 64);
alter table public.events add column if not exists aal text check (aal is null or aal in ('aal1', 'aal2', 'aal3'));
alter table public.events add column if not exists error_code text check (error_code is null or error_code ~ '^[a-z_]{1,40}$');
alter table public.events add column if not exists signed_at text check (signed_at is null or char_length(signed_at) <= 40);
alter table public.events add column if not exists key_id text check (key_id is null or key_id ~ '^[0-9a-f]{16}$');
alter table public.events add column if not exists signature text check (signature is null or char_length(signature) <= 300);
create index if not exists events_action_time on public.events(action, occurred_at desc);

-- The chain hash now also covers the new columns. Each is appended only when non-null, so rows
-- written before this migration still verify with the original formula.
create or replace function public.event_row_hash(e public.events) returns text
language sql immutable set search_path = public, extensions, pg_temp as $$
  select encode(digest(
    e.prev_hash || '|' || e.occurred_at::text || '|' || coalesce(e.actor_id::text, '') || '|' ||
    e.action || '|' || e.entity_type || '|' || coalesce(e.entity_id, '') || '|' ||
    e.outcome || '|' || e.details::text ||
    coalesce('|ip=' || e.source_ip, '') || coalesce('|sid=' || e.session_id, '') || coalesce('|aal=' || e.aal, '') ||
    coalesce('|err=' || e.error_code, '') || coalesce('|ts=' || e.signed_at, '') || coalesce('|kid=' || e.key_id, '') ||
    coalesce('|sig=' || e.signature, ''), 'sha256'), 'hex')
$$;

create or replace function public.events_hash_chain() returns trigger
language plpgsql security definer set search_path = public, extensions, pg_temp as $$
declare
  last_hash text;
begin
  perform pg_advisory_xact_lock(hashtext('public.events'));
  select e.hash into last_hash from public.events e order by e.id desc limit 1;
  new.prev_hash := coalesce(last_hash, repeat('0', 64));
  new.occurred_at := clock_timestamp();
  new.hash := public.event_row_hash(new);
  return new;
end $$;

create or replace function public.verify_event_chain() returns bigint
language plpgsql stable security definer set search_path = public, extensions, pg_temp as $$
declare
  r public.events;
  expected_prev text := repeat('0', 64);
begin
  for r in select * from public.events order by id loop
    if r.prev_hash is distinct from expected_prev or r.hash <> public.event_row_hash(r) then
      return r.id;
    end if;
    expected_prev := r.hash;
  end loop;
  return null;
end $$;
revoke execute on function public.event_row_hash(public.events) from public, anon, authenticated;
grant execute on function public.verify_event_chain() to acme_api;

-- Belt and braces: nobody may rewrite history (the trigger also blocks the table owner's DML).
do $$
declare r text;
begin
  foreach r in array array['public', 'anon', 'authenticated', 'acme_api', 'acme_reporting', 'service_role'] loop
    if r = 'public' or exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke update, delete, truncate on public.events from %s', case when r = 'public' then 'public' else quote_ident(r) end);
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 2. Administrator alerts for audit/logging failures, integrity violations, watchdog (T431, T345)
-- ---------------------------------------------------------------------------
create table if not exists public.system_alerts (
  id uuid primary key default gen_random_uuid(),
  raised_at timestamptz not null default clock_timestamp(),
  kind text not null check (kind ~ '^[a-z_]{1,40}$'),
  severity text not null check (severity in ('warning', 'critical')),
  details jsonb not null default '{}'::jsonb check (pg_column_size(details) <= 4096),
  acknowledged_at timestamptz,
  acknowledged_by uuid references public.staff_profiles(user_id)
);
create index if not exists system_alerts_open on public.system_alerts(raised_at desc) where acknowledged_at is null;
alter table public.system_alerts enable row level security;
alter table public.system_alerts force row level security;
revoke all on public.system_alerts from anon, authenticated;
grant select, insert on public.system_alerts to acme_api;
grant update (acknowledged_at, acknowledged_by) on public.system_alerts to acme_api;
drop policy if exists alerts_insert on public.system_alerts;
create policy alerts_insert on public.system_alerts for insert to acme_api with check (acknowledged_at is null);
drop policy if exists alerts_read on public.system_alerts;
create policy alerts_read on public.system_alerts for select to acme_api using (public.current_staff_role() = 'admin');
drop policy if exists alerts_ack on public.system_alerts;
create policy alerts_ack on public.system_alerts for update to acme_api
  using (public.current_staff_role() = 'admin') with check (acknowledged_by = public.current_staff_id());

-- ---------------------------------------------------------------------------
-- 3. Configuration integrity MACs written only by the backend (T345)
-- ---------------------------------------------------------------------------
alter table public.alarm_thresholds add column if not exists integrity_mac text
  check (integrity_mac is null or integrity_mac ~ '^[0-9a-f]{64}$');
alter table public.simulation_state add column if not exists integrity_mac text
  check (integrity_mac is null or integrity_mac ~ '^[0-9a-f]{64}$');
grant update (integrity_mac) on public.alarm_thresholds to acme_api;
grant update (integrity_mac) on public.simulation_state to acme_api;

-- ---------------------------------------------------------------------------
-- 4. Fail-safe alarm for evaluation errors (T347)
-- ---------------------------------------------------------------------------
alter type public.alarm_type add value if not exists 'evaluation_error';

-- ---------------------------------------------------------------------------
-- 5. Heartbeat watchdog (T4602): a bound, online monitor that stops sending data for longer
-- than the timeout is marked offline and gets a HIGH connection_lost alarm, independently of the
-- simulation scenario. Runs from pg_cron when available and on API access/simulation ticks.
-- ---------------------------------------------------------------------------
create or replace function public.watchdog_sweep(p_timeout_seconds integer default 30)
returns table (lost_monitor_id uuid, alarm_raised boolean)
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if p_timeout_seconds < 10 or p_timeout_seconds > 600 then
    raise exception 'invalid watchdog timeout';
  end if;
  -- Same lock as simulation ticks/reset: never interleaves with them (T205/T633); skip if busy.
  if not pg_try_advisory_xact_lock(hashtext('acme:simulation')) then
    return;
  end if;
  return query
  with lost as (
    update public.monitors m set status = 'offline'
     where m.status = 'online'
       and (m.last_heartbeat_at is null or m.last_heartbeat_at < now() - make_interval(secs => p_timeout_seconds))
       and exists (select 1 from public.monitor_assignments ma where ma.monitor_id = m.id and ma.unassigned_at is null)
    returning m.id),
  raised as (
    insert into public.alarms (patient_id, monitor_id, type, priority, message)
    select p.id, l.id, 'connection_lost', 'high', 'Monitor connection lost: no data received (watchdog)'
      from lost l
      left join public.monitor_assignments ma on ma.monitor_id = l.id and ma.unassigned_at is null
      left join public.patients p on p.bed_id = ma.bed_id and p.discharged_at is null
    on conflict (monitor_id, type) where state = 'active' do update set last_seen_at = now()
    returning alarms.monitor_id)
  select l.id, exists (select 1 from raised r where r.monitor_id = l.id) from lost l;
end $$;
revoke execute on function public.watchdog_sweep(integer) from public, anon, authenticated;
grant execute on function public.watchdog_sweep(integer) to acme_api;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.unschedule(jobid) from cron.job where jobname = 'acme-watchdog';
    perform cron.schedule('acme-watchdog', '10 seconds', 'select public.watchdog_sweep(30)');
  end if;
end $$;
