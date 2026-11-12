-- 0012_device_auth_lockout.sql - throttling and lockout of system (device) accounts (T70). Idempotent.
--
-- Simulated bedside monitors are system accounts that prove their identity with a per-device secret
-- (0006_auth.sql). Failed verifications are counted in the database (private.device_auth_failures), so every
-- Vercel instance sees the same state. This migration replaces the fixed 15-minute lock with an exponential
-- back-off: after 5 consecutive failures the device is locked for 15 minutes, and every further failed
-- attempt after a lock expires doubles the lock (30 min, 1 h, 2 h, ...), capped at 24 hours. A successful
-- verification resets the counter. Administrators can lift a lock (audited by the API).
--
-- "Locked", "unknown monitor" and "wrong secret" all return false, so the caller cannot tell them apart.

alter table private.device_auth_failures add column if not exists lockouts integer not null default 0;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'device_auth_failures_lockouts_check') then
    alter table private.device_auth_failures add constraint device_auth_failures_lockouts_check check (lockouts >= 0);
  end if;
end $$;

create or replace function public.verify_monitor_secret(p_monitor uuid, p_secret text) returns boolean
language plpgsql security definer set search_path = public, extensions, pg_temp as $$
declare
  v_hash bytea;
  v_status text;
  v_fail private.device_auth_failures;
begin
  if public.current_staff_role() is null then
    raise exception 'permission denied' using errcode = '42501';
  end if;
  select device_secret_hash, status::text into v_hash, v_status from public.monitors where id = p_monitor for update;
  if v_hash is null then
    return false;
  end if;
  select * into v_fail from private.device_auth_failures where monitor_id = p_monitor;
  if v_fail.locked_until is not null and v_fail.locked_until > now() then
    return false;  -- locked: same answer as a wrong secret, and not counted
  end if;
  if v_status <> 'retired' and p_secret is not null and char_length(p_secret) between 16 and 256
     and digest(convert_to(p_secret, 'UTF8'), 'sha256') = v_hash then
    delete from private.device_auth_failures where monitor_id = p_monitor;
    update public.monitors set authenticated_at = now() where id = p_monitor;
    return true;
  end if;
  -- Exponential back-off: 15 min * 2^(previous lockouts), capped at 24 hours.
  insert into private.device_auth_failures as f (monitor_id, failures) values (p_monitor, 1)
  on conflict (monitor_id) do update
    set failures = f.failures + 1,
        lockouts = f.lockouts + case when f.failures + 1 >= 5 then 1 else 0 end,
        locked_until = case when f.failures + 1 >= 5
          then now() + least(interval '24 hours', interval '15 minutes' * power(2, least(f.lockouts, 7)))
          else f.locked_until end,
        updated_at = now();
  return false;
end $$;

-- True while the monitor's secret verification is locked (used by the API to audit the lockout and alert
-- administrators after a failed attempt; never returned to the caller).
create or replace function public.monitor_auth_locked(p_monitor uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select public.current_staff_role() is not null and exists (
    select 1 from private.device_auth_failures f where f.monitor_id = p_monitor and f.locked_until > now())
$$;

-- Administrator unlock (settings:manage). Clears the counter and the back-off history.
create or replace function public.unlock_monitor_auth(p_monitor uuid) returns boolean
language plpgsql security definer set search_path = public, pg_temp as $$
declare v_count integer;
begin
  if not public.has_permission('settings:manage') then
    raise exception 'permission denied' using errcode = '42501';
  end if;
  delete from private.device_auth_failures where monitor_id = p_monitor;
  get diagnostics v_count = row_count;
  return v_count > 0;
end $$;

revoke execute on function public.verify_monitor_secret(uuid, text), public.monitor_auth_locked(uuid),
  public.unlock_monitor_auth(uuid) from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke execute on function public.verify_monitor_secret(uuid, text), public.monitor_auth_locked(uuid), '
            'public.unlock_monitor_auth(uuid) from anon, authenticated';
  end if;
  if exists (select 1 from pg_roles where rolname = 'acme_api_rw') then
    execute 'grant execute on function public.verify_monitor_secret(uuid, text), public.monitor_auth_locked(uuid), '
            'public.unlock_monitor_auth(uuid) to acme_api_rw';
  end if;
end $$;
