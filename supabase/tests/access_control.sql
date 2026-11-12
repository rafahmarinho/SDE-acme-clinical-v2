-- Live database access-control checks (T19, T2598). Run by the CI `db-drill` job against a fresh
-- local Supabase stack, connected AS the API login role `acme_api`:
--   psql "postgresql://acme_api:<ci password>@127.0.0.1:54322/postgres" -v ON_ERROR_STOP=1 -f supabase/tests/access_control.sql
-- Every block raises (failing the job) when a control is missing. Read-only: forbidden statements are
-- expected to fail with insufficient_privilege before touching data.

\set ON_ERROR_STOP on

-- 1. The runtime role is least privilege (no superuser, no RLS bypass).
do $$
declare v_super boolean; v_bypass boolean;
begin
  if current_user <> 'acme_api' then
    raise exception 'access_control.sql must run as acme_api, not %', current_user;
  end if;
  select rolsuper, rolbypassrls into v_super, v_bypass from pg_roles where rolname = current_user;
  if v_super or v_bypass then
    raise exception 'acme_api must be NOSUPERUSER NOBYPASSRLS';
  end if;
end $$;

-- 2. Forbidden statements fail with a permission error (T19).
do $$
declare stmt text;
begin
  foreach stmt in array array[
    'delete from public.events',
    'truncate public.events',
    'update public.events set action = action',
    'delete from private.device_auth_failures',
    'update public.observations set body = body',
    'delete from public.patients',
    'delete from public.observations',
    'delete from public.alarms',
    'select count(*) from auth.users',
    'drop table public.patients',
    'create table public.ci_probe (id int)',
    'alter table public.patients disable row level security'
  ] loop
    begin
      execute stmt;
      raise exception 'statement unexpectedly allowed for acme_api: %', stmt;
    exception when insufficient_privilege then
      null;  -- expected
    end;
  end loop;
end $$;

-- 3. Row-level security is on for every public table (T2598).
do $$
declare v_tables text;
begin
  select string_agg(c.relname, ', ') into v_tables
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity;
  if v_tables is not null then
    raise exception 'tables without row level security: %', v_tables;
  end if;
end $$;

-- 4. Without verified staff claims (app.user_id unset) the API role sees no clinical or staff rows.
do $$
declare n integer;
begin
  perform set_config('app.user_id', '', true);
  select count(*) into n from public.patients;
  if n <> 0 then raise exception 'patients visible without staff claims: % rows', n; end if;
  select count(*) into n from public.observations;
  if n <> 0 then raise exception 'observations visible without staff claims: % rows', n; end if;
  select count(*) into n from public.attachments;
  if n <> 0 then raise exception 'attachments visible without staff claims: % rows', n; end if;
  select count(*) into n from public.staff_profiles;
  if n <> 0 then raise exception 'staff profiles visible without staff claims: % rows', n; end if;
end $$;

select 'access_control.sql: all checks passed' as result;
