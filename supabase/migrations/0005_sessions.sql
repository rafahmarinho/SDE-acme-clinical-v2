-- ACME Clinical: server-side session management (skills/session-management). Idempotent.
--
-- Supabase Auth issues the session (auth.sessions row + refresh token; the access JWT carries the
-- `session_id` claim). This migration adds the application-side bookkeeping the API needs to:
--   * limit concurrent sessions per account, revoking the OLDEST sessions first (T429/T430);
--   * enforce the idle timeout server-side from real user activity only (T24/T90);
--   * enforce the absolute timeout from the session start, not from the refreshed JWT (T25/T92);
--   * make logout / "sign out everywhere" kill the refresh token immediately (T26/T93);
--   * close direct Supabase access (Realtime / PostgREST) for revoked sessions via RLS (T26).
-- Writes happen only through SECURITY DEFINER functions executable by the API group role
-- (acme_api_rw, inherited by the acme_api login role); browsers have no access to app_sessions.
-- See docs/security/sessions.md.

-- ---------------------------------------------------------------------------
-- 1. Previous/last login naming fix: the API used to write the CURRENT ip into previous_login_ip.
-- ---------------------------------------------------------------------------
alter table public.staff_profiles add column if not exists last_login_ip inet;
grant update (last_login_ip) on public.staff_profiles to acme_api_rw;

-- ---------------------------------------------------------------------------
-- 2. Application session registry, keyed by the Supabase JWT session_id (never by user_id)
-- ---------------------------------------------------------------------------
create table if not exists public.app_sessions (
  session_id uuid primary key,
  user_id uuid not null references public.staff_profiles(user_id) on delete cascade,
  created_at timestamptz not null default now(),
  last_activity_at timestamptz not null default now(),
  revoked_at timestamptz,
  revoked_reason text check (revoked_reason in ('logout', 'logout_all', 'concurrent_limit', 'idle_timeout',
                                                'absolute_timeout', 'signed_out', 'admin')),
  user_agent text check (char_length(user_agent) <= 256),
  ip_hash text check (char_length(ip_hash) <= 128),
  check ((revoked_at is null) = (revoked_reason is null))
);
create index if not exists app_sessions_user_created on public.app_sessions (user_id, created_at desc);

alter table public.app_sessions enable row level security;
alter table public.app_sessions force row level security;
revoke all on public.app_sessions from public, anon, authenticated;
grant select on public.app_sessions to acme_api_rw;  -- no direct insert/update/delete: functions below only

drop policy if exists app_sessions_read on public.app_sessions;
create policy app_sessions_read on public.app_sessions for select to acme_api
  using (user_id = public.current_staff_id() or public.has_permission('staff:manage'));

-- ---------------------------------------------------------------------------
-- 3. Functions (SECURITY DEFINER, fixed search_path, identity from current_staff_id())
-- ---------------------------------------------------------------------------

-- Register the caller's freshly issued Supabase session and enforce the concurrent-session limit.
-- The current (newest) session always wins; older live Supabase sessions beyond the limit are revoked
-- and their auth.sessions rows deleted, which also invalidates their refresh tokens.
-- Limit: security_settings.max_concurrent_sessions, capped at 1 for administrators.
create or replace function public.register_session(p_session uuid, p_user_agent text, p_ip_hash text)
returns table (status text, created boolean, revoked_count integer, previous_unclosed boolean)
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_user uuid := public.current_staff_id();
  v_role public.app_role := public.current_staff_role();
  v_row public.app_sessions;
  v_limit integer;
  v_stale uuid[];
  v_prev_reason text;
  v_prev_found boolean;
begin
  if v_user is null or v_role is null or p_session is null then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  -- Serialise registrations per user so parallel logins cannot race past the limit.
  perform pg_advisory_xact_lock(hashtextextended('acme.sessions:' || v_user::text, 0));

  select * into v_row from public.app_sessions a where a.session_id = p_session;
  if found then
    if v_row.user_id <> v_user then
      raise exception 'not authorized' using errcode = '42501';
    end if;
    -- Idempotent: an already registered session is never resurrected or re-counted.
    return query select case when v_row.revoked_at is null then 'active' else 'revoked' end, false, 0, false;
    return;
  end if;

  -- The session must be live in Supabase Auth and belong to the caller.
  if not exists (select 1 from auth.sessions s where s.id = p_session and s.user_id = v_user) then
    return query select 'revoked'::text, false, 0, false;
    return;
  end if;

  select a.revoked_reason, true into v_prev_reason, v_prev_found
  from public.app_sessions a where a.user_id = v_user order by a.created_at desc limit 1;

  insert into public.app_sessions (session_id, user_id, user_agent, ip_hash)
  values (p_session, v_user, left(p_user_agent, 256), left(p_ip_hash, 128));

  select case when v_role = 'admin' then least(s.max_concurrent_sessions, 1) else s.max_concurrent_sessions end
    into v_limit from public.security_settings s where s.id = 1;
  v_limit := greatest(coalesce(v_limit, 1), 1);

  select coalesce(array_agg(x.id), '{}') into v_stale from (
    select s.id from auth.sessions s
    where s.user_id = v_user and s.id <> p_session
    order by s.created_at desc, s.id
    offset v_limit - 1
  ) x;

  update public.app_sessions a set revoked_at = now(), revoked_reason = 'concurrent_limit'
  where a.session_id = any(v_stale) and a.revoked_at is null;
  delete from auth.sessions s where s.id = any(v_stale) and s.user_id = v_user;

  return query select 'active'::text, true, cardinality(v_stale),
    coalesce(v_prev_found, false) and (v_prev_reason is null or v_prev_reason not in ('logout', 'logout_all'));
end $$;

-- State of one of the caller's sessions, including whether Supabase Auth still knows it.
create or replace function public.session_state(p_session uuid)
returns table (created_at timestamptz, last_activity_at timestamptz, revoked_at timestamptz,
               revoked_reason text, auth_session_exists boolean, idle_minutes smallint, absolute_hours smallint)
language sql stable security definer set search_path = public, pg_temp as $$
  select a.created_at, a.last_activity_at, a.revoked_at, a.revoked_reason,
         exists (select 1 from auth.sessions s where s.id = a.session_id),
         st.session_idle_minutes, st.session_absolute_hours
  from public.app_sessions a cross join public.security_settings st
  where a.session_id = p_session and a.user_id = public.current_staff_id() and st.id = 1
$$;

-- Record real user activity (heartbeat). Never resurrects a revoked session.
create or replace function public.touch_session(p_session uuid) returns boolean
language sql volatile security definer set search_path = public, pg_temp as $$
  update public.app_sessions a set last_activity_at = now()
  where a.session_id = p_session and a.user_id = public.current_staff_id() and a.revoked_at is null
  returning true
$$;

-- Revoke one session (own session, or any session for staff managers) and kill its refresh token.
create or replace function public.revoke_session(p_session uuid, p_reason text) returns boolean
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_user uuid := public.current_staff_id();
  v_owner uuid;
begin
  if v_user is null then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  select a.user_id into v_owner from public.app_sessions a where a.session_id = p_session;
  if v_owner is null or (v_owner <> v_user and not public.has_permission('staff:manage')) then
    return false;
  end if;
  update public.app_sessions a set revoked_at = now(), revoked_reason = p_reason
  where a.session_id = p_session and a.revoked_at is null;
  delete from auth.sessions s where s.id = p_session and s.user_id = v_owner;
  return true;
end $$;

-- "Sign out everywhere": revoke every session of the caller and delete all their refresh tokens.
create or replace function public.revoke_user_sessions(p_reason text) returns integer
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_user uuid := public.current_staff_id();
  v_count integer;
begin
  if v_user is null then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  update public.app_sessions a set revoked_at = now(), revoked_reason = p_reason
  where a.user_id = v_user and a.revoked_at is null;
  delete from auth.sessions s where s.user_id = v_user;
  get diagnostics v_count = row_count;
  return v_count;
end $$;

-- RLS helper for direct browser access (Realtime/PostgREST): the JWT's session must be registered,
-- not revoked and still known to Supabase Auth.
create or replace function public.app_session_active() returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists (
    select 1 from public.app_sessions a join auth.sessions s on s.id = a.session_id
    where a.session_id = nullif(auth.jwt() ->> 'session_id', '')::uuid
      and a.user_id = auth.uid() and a.revoked_at is null)
$$;

revoke execute on function public.register_session(uuid, text, text), public.session_state(uuid),
  public.touch_session(uuid), public.revoke_session(uuid, text), public.revoke_user_sessions(text),
  public.app_session_active() from public, anon, authenticated;
grant execute on function public.register_session(uuid, text, text), public.session_state(uuid),
  public.touch_session(uuid), public.revoke_session(uuid, text), public.revoke_user_sessions(text)
  to acme_api_rw;
grant execute on function public.app_session_active() to authenticated;

-- ---------------------------------------------------------------------------
-- 4. Revoked sessions lose direct Supabase access too (restrictive: AND-ed with existing policies)
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['wards', 'beds', 'monitors', 'monitor_assignments', 'readings', 'alarms'] loop
    execute format('drop policy if exists %I on public.%I', t || '_session_active', t);
    execute format('create policy %I on public.%I as restrictive for select to authenticated using (public.app_session_active())',
                   t || '_session_active', t);
  end loop;
end $$;
