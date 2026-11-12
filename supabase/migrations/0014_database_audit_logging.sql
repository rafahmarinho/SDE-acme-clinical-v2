-- 0014_database_audit_logging.sql - database activity logging for the application roles (T2602). Idempotent.
--
-- Complements the application's signed, hash-chained public.events table with server-side statement logging
-- in the Supabase-managed Postgres log (Logs Explorer / log drains):
--   * pgaudit logs every data change (write), schema change (ddl) and privilege change (role) issued by the
--     API login role and the data-lifecycle role, with the role, database, statement and object name;
--   * `read` is deliberately NOT logged: SELECTs on patient tables would copy PHI into the platform log (T46);
--   * pgaudit.log_parameter stays off so bound values (patient names, observation text) never reach the log;
--     the statement text identifies the operation, and public.events records who/what/when with ids.
-- Server start/stop/pause, connection logging and log retention are Supabase platform settings: see the
-- operator checklist in docs/security/logging-audit.md ("Database server logging").

do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'pgaudit') then
    create extension if not exists pgaudit;
  else
    raise notice 'pgaudit is not available on this server: database statement logging is not enabled';
  end if;
exception when insufficient_privilege then
  raise notice 'pgaudit could not be enabled by %; enable it in Dashboard > Database > Extensions', current_user;
end $$;

do $$
declare r text;
begin
  if exists (select 1 from pg_extension where extname = 'pgaudit') then
    foreach r in array array['acme_api', 'acme_api_rw', 'acme_reset_owner'] loop
      if exists (select 1 from pg_roles where rolname = r) then
        execute format('alter role %I set pgaudit.log = %L', r, 'write, ddl, role');
        execute format('alter role %I set pgaudit.log_parameter = %L', r, 'off');
        execute format('alter role %I set pgaudit.log_relation = %L', r, 'on');
      end if;
    end loop;
  end if;
exception when insufficient_privilege then
  raise notice 'role-level pgaudit settings could not be applied by %; apply them as the project owner', current_user;
end $$;
