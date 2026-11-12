-- 0009_rate_limits.sql - shared, per-user message throttling for expensive API operations (T1362).
--
-- Vercel runs the API as many short-lived instances, so the in-memory token buckets in
-- backend/app/core/middleware.py only bound a single instance. Expensive operations (simulation control,
-- reports, uploads) additionally consume a fixed-window budget stored here, keyed on the VERIFIED caller id
-- (app.user_id set by backend/app/db.py), so the limit holds across instances and across token rotation.
-- Idempotent: safe to re-run.

create schema if not exists private;
revoke all on schema private from public;

create table if not exists private.rate_limit_buckets (
  bucket       text        not null,
  window_start timestamptz not null,
  hits         integer     not null default 0,
  primary key (bucket, window_start),
  constraint rate_limit_bucket_len check (char_length(bucket) between 1 and 120)
);
-- RLS on with no policies: only the function owner (via the SECURITY DEFINER function) can touch rows.
alter table private.rate_limit_buckets enable row level security;
revoke all on private.rate_limit_buckets from public, anon, authenticated;

-- Consume one request from "<name>:<caller>" for the current one-minute window.
-- Returns 0 when allowed, otherwise the number of seconds until the window resets (Retry-After).
-- The caller id is taken from the transaction (app.user_id), never from the argument, so one user cannot
-- drain another user's budget.
create or replace function public.consume_rate_limit(p_name text, p_per_minute integer)
returns integer
language plpgsql security definer set search_path = private, public, pg_temp as $$
declare
  v_user   text := nullif(current_setting('app.user_id', true), '');
  v_window timestamptz := date_trunc('minute', now());
  v_hits   integer;
begin
  if p_name !~ '^[a-z][a-z0-9-]{0,40}$' or p_per_minute < 1 or p_per_minute > 10000 then
    raise exception 'invalid rate limit parameters';
  end if;
  if v_user is null then
    raise exception 'rate limit requires an authenticated caller';
  end if;
  insert into private.rate_limit_buckets as b (bucket, window_start, hits)
  values (p_name || ':' || v_user, v_window, 1)
  on conflict (bucket, window_start) do update set hits = b.hits + 1
  returning b.hits into v_hits;
  -- opportunistic cleanup of windows older than ten minutes
  delete from private.rate_limit_buckets where window_start < now() - interval '10 minutes';
  if v_hits > p_per_minute then
    return greatest(1, ceil(extract(epoch from (v_window + interval '1 minute' - now())))::integer);
  end if;
  return 0;
end $$;

revoke execute on function public.consume_rate_limit(text, integer) from public, anon, authenticated;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'acme_api_rw') then
    execute 'grant execute on function public.consume_rate_limit(text, integer) to acme_api_rw';
  end if;
end $$;
