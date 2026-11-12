-- 0011_session_reset_on_privilege_change.sql - reset old sessions after a privilege change (T20).
--
-- New sessions get fresh random ids at every sign-in (register_session, 0005). When an administrator changes
-- another user's role or deactivates the account, every session that user already holds is revoked
-- (app_sessions) and removed from Supabase Auth (auth.sessions, which also kills the refresh tokens), so the
-- next request with an old token is rejected and the user must sign in again under the new privileges.
-- Idempotent.

create or replace function public.revoke_sessions_for_user(p_user uuid) returns integer
language plpgsql volatile security definer set search_path = public, pg_temp as $$
declare
  v_count integer;
begin
  if not public.has_permission('staff:manage') then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  if p_user is null or p_user = public.current_staff_id() then
    raise exception 'invalid target' using errcode = '22023';
  end if;
  update public.app_sessions a set revoked_at = now(), revoked_reason = 'admin'
  where a.user_id = p_user and a.revoked_at is null;
  delete from auth.sessions s where s.user_id = p_user;
  get diagnostics v_count = row_count;
  return v_count;
end $$;

revoke execute on function public.revoke_sessions_for_user(uuid) from public, anon, authenticated;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'acme_api_rw') then
    execute 'grant execute on function public.revoke_sessions_for_user(uuid) to acme_api_rw';
  end if;
end $$;
