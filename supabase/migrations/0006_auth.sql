-- ACME Clinical: authentication hardening (idempotent). See docs/security/authentication.md.
--
-- * Passwords are never stored by the application: Supabase Auth keeps salted bcrypt hashes in
--   auth.users.encrypted_password. No table in public/private has a password column (tested).
-- * Canonical staff e-mail addresses (trimmed, lower-case, ASCII, no invisible characters) so the API,
--   Supabase Auth and the database apply one username rule (T286/T287). Identity is the auth.users UUID.
-- * Account lockout: Supabase Auth "password verification attempt" hook counts consecutive failures per
--   account and soft-locks it (lockout_threshold / lockout_minutes from public.security_settings,
--   doubling on repeated lock-outs, capped at 8x). The hook never reveals the lock: the client gets the
--   same generic error as for a wrong password (T6/T8). Administrators can unlock (audited by the API).
-- * Login history for the previous-login notice: failed attempts since the previous successful sign-in
--   (T427). Kept 90 days, unreachable from the Data API (private schema).
-- * Monitor (device) authenticity: a monitor proves possession of its per-device secret (pairing code);
--   only SHA-256 hashes are stored. Verification is throttled per device in the database, so the limit
--   is shared by every serverless instance (T425/T426/T114).

create schema if not exists private;
revoke all on schema private from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on schema private from anon, authenticated';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 1. One username rule: canonical, unique e-mail per person
-- ---------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'staff_profiles_email_canonical') then
    alter table public.staff_profiles add constraint staff_profiles_email_canonical check (
      email::text = lower(btrim(email::text))
      and email::text ~ '^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'
      and char_length(email::text) <= 254);
  end if;
end $$;
-- staff_profiles.email is citext UNIQUE (case-insensitive) and user_id is the auth.users PK:
-- one auth user = one profile = one person; no shared or role-named accounts are created by any seed.

-- ---------------------------------------------------------------------------
-- 2. Account lockout and login history (written only by Supabase Auth through the hook)
-- ---------------------------------------------------------------------------
create table if not exists private.auth_lockouts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
  locked_until timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists private.login_attempts (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  success boolean not null,
  created_at timestamptz not null default now()
);
create index if not exists login_attempts_user_time on private.login_attempts (user_id, created_at desc);

revoke all on private.auth_lockouts, private.login_attempts from public;

create or replace function public.hook_password_verification_attempt(event jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_user uuid := (event ->> 'user_id')::uuid;
  v_valid boolean := coalesce((event ->> 'valid')::boolean, false);
  v_threshold integer;
  v_minutes integer;
  v_row private.auth_lockouts;
begin
  select s.lockout_threshold, s.lockout_minutes into v_threshold, v_minutes
  from public.security_settings s where s.id = 1;
  v_threshold := coalesce(v_threshold, 5);
  v_minutes := coalesce(v_minutes, 15);

  insert into private.login_attempts (user_id, success) values (v_user, v_valid and not exists (
    select 1 from private.auth_lockouts l where l.user_id = v_user and l.locked_until > now()));
  delete from private.login_attempts where user_id = v_user and created_at < now() - interval '90 days';

  select * into v_row from private.auth_lockouts where user_id = v_user for update;

  if v_row.locked_until is not null and v_row.locked_until > now() then
    -- Locked: refuse even the correct password, with the same generic text as a wrong password.
    update private.auth_lockouts set consecutive_failures = consecutive_failures + (case when v_valid then 0 else 1 end),
                                      updated_at = now()
    where user_id = v_user;
    return jsonb_build_object('decision', 'reject', 'message', 'Invalid login credentials', 'should_logout_user', false);
  end if;

  if v_valid then
    delete from private.auth_lockouts where user_id = v_user;
    return jsonb_build_object('decision', 'continue');
  end if;

  insert into private.auth_lockouts as l (user_id, consecutive_failures) values (v_user, 1)
  on conflict (user_id) do update set consecutive_failures = l.consecutive_failures + 1, updated_at = now()
  returning * into v_row;

  if v_row.consecutive_failures >= v_threshold then
    update private.auth_lockouts
    set locked_until = now() + make_interval(mins => v_minutes * least(8, power(2, v_row.consecutive_failures - v_threshold)::integer))
    where user_id = v_user;
  end if;
  return jsonb_build_object('decision', 'continue');
end $$;

revoke execute on function public.hook_password_verification_attempt(jsonb) from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke execute on function public.hook_password_verification_attempt(jsonb) from anon, authenticated';
  end if;
  if exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    execute 'grant usage on schema private to supabase_auth_admin';
    execute 'grant select, insert, update, delete on private.auth_lockouts, private.login_attempts to supabase_auth_admin';
    execute 'grant usage on sequence private.login_attempts_id_seq to supabase_auth_admin';
    execute 'grant select on public.security_settings to supabase_auth_admin';
    execute 'grant execute on function public.hook_password_verification_attempt(jsonb) to supabase_auth_admin';
  end if;
end $$;

-- Administrator unlock (the API audits the call). Never touches Supabase Auth bans (hard locks).
create or replace function public.unlock_staff_account(p_user uuid) returns boolean
language plpgsql security definer set search_path = public, pg_temp as $$
declare v_count integer;
begin
  if public.current_staff_role() is distinct from 'admin' then
    raise exception 'permission denied' using errcode = '42501';
  end if;
  delete from private.auth_lockouts where user_id = p_user;
  get diagnostics v_count = row_count;
  return v_count > 0;
end $$;

-- Previous-login notice: failed attempts between the previous and the current successful sign-in.
create or replace function public.login_activity_summary(p_user uuid)
returns table (failed_since_previous_login integer, last_failed_at timestamptz)
language sql stable security definer set search_path = public, pg_temp as $$
  with mine as (
    select a.success, a.created_at from private.login_attempts a
    where a.user_id = p_user and (p_user = public.current_staff_id() or public.current_staff_role() = 'admin')
  ), prev_success as (
    select created_at from mine where success order by created_at desc offset 1 limit 1
  )
  select count(*)::integer, max(m.created_at)
  from mine m
  where not m.success
    and m.created_at > coalesce((select created_at from prev_success), '-infinity'::timestamptz)
$$;

revoke execute on function public.unlock_staff_account(uuid), public.login_activity_summary(uuid) from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke execute on function public.unlock_staff_account(uuid), public.login_activity_summary(uuid) from anon, authenticated';
  end if;
  if exists (select 1 from pg_roles where rolname = 'acme_api_rw') then
    execute 'grant execute on function public.unlock_staff_account(uuid), public.login_activity_summary(uuid) to acme_api_rw';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 3. Monitor (device) authenticity with shared, per-device throttling
-- ---------------------------------------------------------------------------
alter table public.monitors add column if not exists authenticated_at timestamptz;

create table if not exists private.device_auth_failures (
  monitor_id uuid primary key references public.monitors(id) on delete cascade,
  failures integer not null default 0 check (failures >= 0),
  locked_until timestamptz,
  updated_at timestamptz not null default now()
);
revoke all on private.device_auth_failures from public;

-- Returns true only when SHA-256(p_secret) equals the stored device_secret_hash, the monitor is not
-- retired and verification is not locked (5 failures => 15-minute lock, shared by every API instance).
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
    return false;
  end if;
  if v_status <> 'retired' and p_secret is not null and char_length(p_secret) between 16 and 256
     and digest(convert_to(p_secret, 'UTF8'), 'sha256') = v_hash then
    delete from private.device_auth_failures where monitor_id = p_monitor;
    update public.monitors set authenticated_at = now() where id = p_monitor;
    return true;
  end if;
  insert into private.device_auth_failures as f (monitor_id, failures) values (p_monitor, 1)
  on conflict (monitor_id) do update set failures = f.failures + 1, updated_at = now(),
    locked_until = case when f.failures + 1 >= 5 then now() + interval '15 minutes' else f.locked_until end;
  return false;
end $$;

revoke execute on function public.verify_monitor_secret(uuid, text) from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke execute on function public.verify_monitor_secret(uuid, text) from anon, authenticated';
  end if;
  if exists (select 1 from pg_roles where rolname = 'acme_api_rw') then
    execute 'grant execute on function public.verify_monitor_secret(uuid, text) to acme_api_rw';
    execute 'grant select (authenticated_at) on public.monitors to acme_api_rw';
  end if;
end $$;
