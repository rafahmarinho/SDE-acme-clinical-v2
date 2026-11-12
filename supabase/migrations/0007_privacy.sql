-- ACME Clinical: privacy controls (skills/privacy). Idempotent.
--
--   * Data classification labels on every column of the personal-data tables (`class=...` comments,
--     checked by backend/tests/test_privacy.py against docs/security/data-classification.md) (T313/T314).
--   * Versioned privacy-notice acknowledgements with evidence rows (T239/T751/T752).
--   * Staff erasure requests: the user asks (API, re-authenticated), a DIFFERENT administrator completes
--     the request; the profile is pseudonymised and deactivated, clinical records the user authored are
--     retained (health-record law) and now point at a pseudonymous profile (T179/T240).
--   * Automated retention: public.run_retention_purge() deletes patients past retention_until (unless
--     on legal hold) with their clinical data, readings/resolved alarms older than
--     security_settings.data_retention_days, and pseudonymises staff deactivated for longer than that
--     period. Runs daily from pg_cron and on demand by administrators; each run writes counts only to
--     public.purge_log (T607/T735).
--   * De-identified reporting views (reporting schema): ward/day aggregates with small-cell suppression
--     (k >= 5) and no patient identifiers or pseudonyms; the reporting role loses raw table access (T545/T745).
--   * Email changes confirmed in Supabase Auth are mirrored to staff_profiles.email (T177).
-- The bulk-delete / pseudonymisation functions are owned by acme_reset_owner (0003), the dedicated
-- non-login data-lifecycle role; the API group role acme_api_rw gets EXECUTE only.

-- ---------------------------------------------------------------------------
-- 1. Columns
-- ---------------------------------------------------------------------------
alter table public.staff_profiles add column if not exists privacy_notice_version text
  check (privacy_notice_version is null or privacy_notice_version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$');
alter table public.staff_profiles add column if not exists erased_at timestamptz;
alter table public.patients add column if not exists legal_hold boolean not null default false;

grant update (privacy_notice_version) on public.staff_profiles to acme_api_rw;
grant update (legal_hold) on public.patients to acme_api_rw;

-- ---------------------------------------------------------------------------
-- 2. Privacy-notice acknowledgements (evidence: who accepted which version, when)
-- ---------------------------------------------------------------------------
create table if not exists public.privacy_consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.staff_profiles(user_id) on delete cascade,
  notice_version text not null check (notice_version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  accepted_at timestamptz not null default now(),
  unique (user_id, notice_version)
);
alter table public.privacy_consents enable row level security;
alter table public.privacy_consents force row level security;

drop policy if exists privacy_consents_read on public.privacy_consents;
create policy privacy_consents_read on public.privacy_consents for select to acme_api_rw
  using (user_id = public.current_staff_id() or public.has_permission('staff:manage'));
drop policy if exists privacy_consents_insert on public.privacy_consents;
create policy privacy_consents_insert on public.privacy_consents for insert to acme_api_rw
  with check (user_id = public.current_staff_id());

grant select, insert on public.privacy_consents to acme_api_rw;

-- ---------------------------------------------------------------------------
-- 3. Data-subject requests (erasure). Completed by another administrator, never by the subject.
-- ---------------------------------------------------------------------------
create table if not exists public.privacy_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.staff_profiles(user_id) on delete cascade,
  kind text not null default 'erasure' check (kind in ('erasure')),
  status text not null default 'pending' check (status in ('pending', 'completed', 'rejected')),
  requested_at timestamptz not null default now(),
  decided_by uuid references public.staff_profiles(user_id),
  decided_at timestamptz,
  check (decided_by is null or decided_by <> user_id),
  check ((status = 'pending') = (decided_at is null))
);
create unique index if not exists privacy_requests_one_pending
  on public.privacy_requests(user_id, kind) where status = 'pending';
alter table public.privacy_requests enable row level security;
alter table public.privacy_requests force row level security;

drop policy if exists privacy_requests_read on public.privacy_requests;
create policy privacy_requests_read on public.privacy_requests for select to acme_api_rw
  using (user_id = public.current_staff_id() or public.has_permission('staff:manage'));
drop policy if exists privacy_requests_insert on public.privacy_requests;
create policy privacy_requests_insert on public.privacy_requests for insert to acme_api_rw
  with check (user_id = public.current_staff_id() and status = 'pending' and decided_by is null);
drop policy if exists privacy_requests_reject on public.privacy_requests;
create policy privacy_requests_reject on public.privacy_requests for update to acme_api_rw
  using (public.has_permission('staff:manage') and status = 'pending' and user_id <> public.current_staff_id())
  with check (decided_by = public.current_staff_id() and status = 'rejected');
drop policy if exists privacy_requests_lifecycle on public.privacy_requests;
create policy privacy_requests_lifecycle on public.privacy_requests for all to acme_reset_owner
  using (true) with check (true);

grant select, insert on public.privacy_requests to acme_api_rw;
grant update (status, decided_by, decided_at) on public.privacy_requests to acme_api_rw;

-- ---------------------------------------------------------------------------
-- 4. Retention evidence, Storage purge queue, approved security-configuration fingerprints
-- ---------------------------------------------------------------------------
create table if not exists public.purge_log (
  id bigserial primary key,
  run_at timestamptz not null default now(),
  run_source text not null check (run_source in ('scheduled', 'manual')),
  counts jsonb not null check (jsonb_typeof(counts) = 'object' and pg_column_size(counts) <= 1024)
);
alter table public.purge_log enable row level security;
alter table public.purge_log force row level security;

-- Object paths of deleted attachments; the API removes them from the private bucket via the Storage API.
create table if not exists public.storage_purge_queue (
  object_path text primary key check (object_path ~ '^patients/[0-9a-f-]{36}/[0-9a-f-]{36}\.(pdf|png|jpg)$'),
  queued_at timestamptz not null default now()
);
alter table public.storage_purge_queue enable row level security;
alter table public.storage_purge_queue force row level security;

create table if not exists public.security_settings_approvals (
  id bigserial primary key,
  fingerprint text not null check (fingerprint ~ '^[0-9a-f]{64}$'),
  approved_by uuid not null references public.staff_profiles(user_id),
  approved_at timestamptz not null default now()
);
alter table public.security_settings_approvals enable row level security;
alter table public.security_settings_approvals force row level security;

drop policy if exists purge_log_read on public.purge_log;
create policy purge_log_read on public.purge_log for select to acme_api_rw
  using (public.has_permission('settings:manage'));
drop policy if exists purge_log_owner on public.purge_log;
create policy purge_log_owner on public.purge_log for all to acme_reset_owner using (true) with check (true);
drop policy if exists storage_queue_read on public.storage_purge_queue;
create policy storage_queue_read on public.storage_purge_queue for select to acme_api_rw
  using (public.has_permission('settings:manage'));
drop policy if exists storage_queue_owner on public.storage_purge_queue;
create policy storage_queue_owner on public.storage_purge_queue for all to acme_reset_owner using (true) with check (true);
drop policy if exists settings_approvals_read on public.security_settings_approvals;
create policy settings_approvals_read on public.security_settings_approvals for select to acme_api_rw
  using (public.has_permission('settings:manage'));
drop policy if exists settings_approvals_insert on public.security_settings_approvals;
create policy settings_approvals_insert on public.security_settings_approvals for insert to acme_api_rw
  with check (public.has_permission('settings:manage') and approved_by = public.current_staff_id());

grant select on public.purge_log, public.storage_purge_queue to acme_api_rw;
grant select, insert on public.security_settings_approvals to acme_api_rw;
grant usage on sequence public.security_settings_approvals_id_seq to acme_api_rw;

-- Lifecycle owner: the only role that bulk-deletes or pseudonymises (through the functions below).
grant select, delete on public.patients, public.attachments, public.staff_ward_assignments to acme_reset_owner;
grant select on public.security_settings, public.wards to acme_reset_owner;
grant select, update (full_name, email, is_active, deactivated_at, last_login_at, previous_login_at,
  previous_login_ip, last_login_ip, privacy_notice_accepted_at, privacy_notice_version, erased_at)
  on public.staff_profiles to acme_reset_owner;
grant select, insert, update, delete on public.privacy_requests to acme_reset_owner;
grant select, insert on public.purge_log to acme_reset_owner;
grant usage on sequence public.purge_log_id_seq to acme_reset_owner;
grant select, insert, delete on public.storage_purge_queue to acme_reset_owner;

drop policy if exists reset_owner_patients on public.patients;
create policy reset_owner_patients on public.patients for all to acme_reset_owner using (true) with check (false);
drop policy if exists reset_owner_attachments on public.attachments;
create policy reset_owner_attachments on public.attachments for all to acme_reset_owner using (true) with check (false);
drop policy if exists reset_owner_staff on public.staff_profiles;
create policy reset_owner_staff on public.staff_profiles for all to acme_reset_owner using (true) with check (true);
drop policy if exists reset_owner_staff_wards on public.staff_ward_assignments;
create policy reset_owner_staff_wards on public.staff_ward_assignments for all to acme_reset_owner using (true) with check (false);
drop policy if exists reset_owner_settings on public.security_settings;
create policy reset_owner_settings on public.security_settings for select to acme_reset_owner using (true);
drop policy if exists reset_owner_wards on public.wards;
create policy reset_owner_wards on public.wards for select to acme_reset_owner using (true);

-- ---------------------------------------------------------------------------
-- 5. Pseudonymisation and retention functions
-- ---------------------------------------------------------------------------
-- Replaces every direct identifier of a staff member; the random UUID key stays so clinical records
-- (observations, acknowledgements, maintenance) remain attributable to "an erased user" only.
create or replace function public.pseudonymise_staff(p_user uuid) returns void
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  update public.staff_profiles
     set full_name = 'Erased user',
         email = 'erased-' || replace(p_user::text, '-', '') || '@erased.invalid',
         is_active = false,
         deactivated_at = coalesce(deactivated_at, now()),
         last_login_at = null, previous_login_at = null, previous_login_ip = null, last_login_ip = null,
         erased_at = now()
   where user_id = p_user and erased_at is null;
  delete from public.staff_ward_assignments where user_id = p_user;
end $$;
revoke execute on function public.pseudonymise_staff(uuid) from public, anon, authenticated;

-- Completes a pending erasure request (administrators with staff:manage; never the subject).
create or replace function public.complete_erasure_request(p_request uuid) returns uuid
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  subject uuid;
begin
  if not public.has_permission('staff:manage') then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  select r.user_id into subject from public.privacy_requests r
   where r.id = p_request and r.status = 'pending' and r.kind = 'erasure' for update;
  if subject is null then
    raise exception 'no pending erasure request' using errcode = 'P0002';
  end if;
  if subject = public.current_staff_id() then
    raise exception 'an erasure request must be completed by another administrator' using errcode = '42501';
  end if;
  perform public.pseudonymise_staff(subject);
  update public.privacy_requests
     set status = 'completed', decided_by = public.current_staff_id(), decided_at = now()
   where id = p_request;
  return subject;
end $$;
revoke execute on function public.complete_erasure_request(uuid) from public, anon, authenticated;

-- Automated destruction of personal data that is no longer needed. Counts only are logged.
create or replace function public.run_retention_purge(p_source text default 'manual') returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  keep_days integer;
  cutoff timestamptz;
  n_patients integer := 0;
  n_files integer := 0;
  n_readings integer := 0;
  n_alarms integer := 0;
  n_staff integer := 0;
  r record;
  result jsonb;
begin
  if public.current_staff_id() is not null then
    if not public.has_permission('settings:manage') then
      raise exception 'not authorized' using errcode = '42501';
    end if;
  elsif session_user not in ('postgres', 'supabase_admin') then
    raise exception 'not authorized' using errcode = '42501';  -- only pg_cron / operators run it unattended
  end if;
  if p_source not in ('scheduled', 'manual') then
    raise exception 'invalid source' using errcode = '22023';
  end if;

  select s.data_retention_days into keep_days from public.security_settings s where s.id = 1;
  cutoff := now() - make_interval(days => coalesce(keep_days, 365));

  -- Patients discharged and past their retention date (not on legal hold): queue their files, then delete
  -- the record; observations, readings, alarms, attachments and break-glass grants cascade.
  insert into public.storage_purge_queue (object_path)
  select a.object_path from public.attachments a join public.patients p on p.id = a.patient_id
   where p.discharged_at is not null and p.retention_until < current_date and not p.legal_hold
  on conflict do nothing;
  get diagnostics n_files = row_count;
  delete from public.patients p
   where p.discharged_at is not null and p.retention_until < current_date and not p.legal_hold;
  get diagnostics n_patients = row_count;

  -- Operational data older than the configured retention period (except for patients on legal hold).
  delete from public.readings rd
   where rd.recorded_at < cutoff
     and not exists (select 1 from public.patients p where p.id = rd.patient_id and p.legal_hold);
  get diagnostics n_readings = row_count;
  delete from public.alarms a
   where a.state = 'resolved' and a.resolved_at < cutoff
     and not exists (select 1 from public.patients p where p.id = a.patient_id and p.legal_hold);
  get diagnostics n_alarms = row_count;

  -- Staff accounts deactivated for longer than the retention period are pseudonymised.
  for r in select sp.user_id from public.staff_profiles sp
            where sp.is_active = false and sp.erased_at is null and sp.deactivated_at < cutoff loop
    perform public.pseudonymise_staff(r.user_id);
    n_staff := n_staff + 1;
  end loop;

  result := jsonb_build_object('patients', n_patients, 'files_queued', n_files, 'readings', n_readings,
                               'alarms', n_alarms, 'staff_pseudonymised', n_staff, 'retention_days', keep_days);
  insert into public.purge_log (run_source, counts) values (p_source, result);
  return result;
end $$;
revoke execute on function public.run_retention_purge(text) from public, anon, authenticated;

-- The API drains the queue and deletes the objects from the private bucket with the Storage API.
create or replace function public.claim_storage_purge_batch(p_limit integer default 100) returns setof text
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if not public.has_permission('settings:manage') then
    raise exception 'not authorized' using errcode = '42501';
  end if;
  return query
    delete from public.storage_purge_queue q
     where q.object_path in (select q2.object_path from public.storage_purge_queue q2
                              order by q2.queued_at limit least(greatest(p_limit, 1), 500))
    returning q.object_path;
end $$;
revoke execute on function public.claim_storage_purge_batch(integer) from public, anon, authenticated;

-- Right of access: references to every record the caller authored, independent of current ward access
-- (RLS would otherwise hide records of patients the caller no longer cares for). Ids and times only:
-- clinical content and patient identity are not returned.
grant select on public.maintenance_records, public.observations to acme_reset_owner;
drop policy if exists reset_owner_maintenance on public.maintenance_records;
create policy reset_owner_maintenance on public.maintenance_records for select to acme_reset_owner using (true);

create or replace function public.my_authored_record_refs()
returns table (kind text, record_id uuid, recorded_at timestamptz)
language sql stable security definer set search_path = public, pg_temp as $$
  select 'observation'::text, o.id, o.created_at from public.observations o
   where o.author_id = public.current_staff_id()
  union all
  select 'alarm_acknowledgement', a.id, a.acknowledged_at from public.alarms a
   where a.acknowledged_by = public.current_staff_id()
  union all
  select 'maintenance', m.id, m.performed_at from public.maintenance_records m
   where m.performed_by = public.current_staff_id()
  union all
  select 'file_upload', f.id, f.created_at from public.attachments f
   where f.uploaded_by = public.current_staff_id()
$$;
revoke execute on function public.my_authored_record_refs() from public, anon, authenticated;

grant execute on function public.has_permission(text), public.current_staff_id(), public.current_staff_role()
  to acme_reset_owner;
grant execute on function public.complete_erasure_request(uuid), public.run_retention_purge(text),
  public.claim_storage_purge_batch(integer), public.my_authored_record_refs() to acme_api_rw;

do $$
begin
  alter function public.my_authored_record_refs() owner to acme_reset_owner;
  alter function public.pseudonymise_staff(uuid) owner to acme_reset_owner;
  alter function public.complete_erasure_request(uuid) owner to acme_reset_owner;
  alter function public.run_retention_purge(text) owner to acme_reset_owner;
  alter function public.claim_storage_purge_batch(integer) owner to acme_reset_owner;
exception when insufficient_privilege then
  raise notice 'privacy lifecycle functions stay owned by %', current_user;
end $$;

-- Daily unattended run (Supabase pg_cron).
do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.unschedule(jobid) from cron.job where jobname = 'acme-retention-purge';
    perform cron.schedule('acme-retention-purge', '15 3 * * *', $job$select public.run_retention_purge('scheduled')$job$);
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 6. Confirmed email changes (Supabase Auth) are mirrored to the profile
-- ---------------------------------------------------------------------------
create or replace function public.sync_staff_email() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if new.email is distinct from old.email and new.email is not null then
    update public.staff_profiles set email = lower(btrim(new.email)) where user_id = new.id;
  end if;
  return new;
end $$;
revoke execute on function public.sync_staff_email() from public, anon, authenticated;

do $$
begin
  if exists (select 1 from pg_namespace where nspname = 'auth') then
    drop trigger if exists acme_sync_staff_email on auth.users;
    create trigger acme_sync_staff_email after update of email on auth.users
      for each row execute function public.sync_staff_email();
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 7. De-identified reporting (secondary use): aggregates only, small cells suppressed (k >= 5)
-- ---------------------------------------------------------------------------
create schema if not exists reporting;
revoke all on schema reporting from public;
grant usage on schema reporting to acme_reporting, acme_api_rw;

grant select on public.alarms, public.readings to acme_reset_owner;
grant usage on schema reporting to acme_reset_owner;

create or replace view reporting.ward_alarm_daily as
select w.code as ward_code, (date_trunc('day', a.raised_at))::date as day, a.type::text as alarm_type,
       a.priority::text as priority, count(*)::int as alarm_count
  from public.alarms a
  join public.patients p on p.id = a.patient_id
  join public.wards w on w.id = p.ward_id
 group by w.code, (date_trunc('day', a.raised_at))::date, a.type, a.priority
having count(*) >= 5;

create or replace view reporting.ward_vitals_daily as
select w.code as ward_code, (date_trunc('day', r.recorded_at))::date as day, count(*)::int as reading_count,
       round(avg(r.heart_rate))::int as mean_heart_rate, round(avg(r.spo2))::int as mean_spo2,
       round(avg(r.resp_rate))::int as mean_resp_rate
  from public.readings r
  join public.patients p on p.id = r.patient_id
  join public.wards w on w.id = p.ward_id
 group by w.code, (date_trunc('day', r.recorded_at))::date
having count(distinct r.patient_id) >= 5;

revoke all on all tables in schema reporting from public, anon, authenticated;
grant select on reporting.ward_alarm_daily, reporting.ward_vitals_daily to acme_reporting, acme_api_rw;
-- The reporting consumer no longer reads raw, patient-linked rows.
revoke select on public.alarms, public.readings from acme_reporting;

do $$
begin
  alter view reporting.ward_alarm_daily owner to acme_reset_owner;
  alter view reporting.ward_vitals_daily owner to acme_reset_owner;
exception when insufficient_privilege then
  raise notice 'reporting views stay owned by %', current_user;
end $$;

-- ---------------------------------------------------------------------------
-- 8. Data classification labels (keep in sync with docs/security/data-classification.md)
-- ---------------------------------------------------------------------------
comment on column public.staff_profiles.user_id is 'class=PII;pii=indirect;random-uuid';
comment on column public.staff_profiles.email is 'class=PII;pii=direct';
comment on column public.staff_profiles.full_name is 'class=PII;pii=direct';
comment on column public.staff_profiles.role is 'class=Internal';
comment on column public.staff_profiles.is_active is 'class=Internal';
comment on column public.staff_profiles.last_login_at is 'class=PII;pii=activity';
comment on column public.staff_profiles.previous_login_at is 'class=PII;pii=activity';
comment on column public.staff_profiles.previous_login_ip is 'class=PII;pii=online-identifier';
comment on column public.staff_profiles.last_login_ip is 'class=PII;pii=online-identifier';
comment on column public.staff_profiles.privacy_notice_accepted_at is 'class=PII;pii=activity';
comment on column public.staff_profiles.privacy_notice_version is 'class=Internal';
comment on column public.staff_profiles.created_at is 'class=Internal';
comment on column public.staff_profiles.updated_at is 'class=Internal';
comment on column public.staff_profiles.deactivated_at is 'class=Internal';
comment on column public.staff_profiles.erased_at is 'class=Internal';

comment on column public.patients.id is 'class=PHI;pii=pseudonymous-key';
comment on column public.patients.pseudonym is 'class=PHI;pii=pseudonym';
comment on column public.patients.display_name is 'class=PHI;pii=direct';
comment on column public.patients.birth_year is 'class=PHI;pii=quasi';
comment on column public.patients.ward_id is 'class=PHI;pii=quasi';
comment on column public.patients.bed_id is 'class=PHI;pii=quasi';
comment on column public.patients.admitted_at is 'class=PHI;pii=quasi';
comment on column public.patients.discharged_at is 'class=PHI;pii=quasi';
comment on column public.patients.retention_until is 'class=Internal';
comment on column public.patients.legal_hold is 'class=Internal';

comment on column public.observations.id is 'class=Internal';
comment on column public.observations.patient_id is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.observations.author_id is 'class=PII;pii=indirect';
comment on column public.observations.body is 'class=PHI;free-text-may-contain-pii';
comment on column public.observations.created_at is 'class=PHI;pii=quasi';

comment on column public.readings.id is 'class=Internal';
comment on column public.readings.monitor_id is 'class=Internal';
comment on column public.readings.patient_id is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.readings.recorded_at is 'class=PHI;pii=quasi';
comment on column public.readings.heart_rate is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.readings.spo2 is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.readings.resp_rate is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.readings.bp_systolic is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.readings.bp_diastolic is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.readings.ecg is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.readings.quality is 'class=Internal';

comment on column public.alarms.id is 'class=Internal';
comment on column public.alarms.patient_id is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.alarms.monitor_id is 'class=Internal';
comment on column public.alarms.type is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.alarms.priority is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.alarms.state is 'class=Internal';
comment on column public.alarms.message is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.alarms.raised_at is 'class=PHI;pii=quasi';
comment on column public.alarms.last_seen_at is 'class=Internal';
comment on column public.alarms.resolved_at is 'class=Internal';
comment on column public.alarms.acknowledged_at is 'class=PII;pii=activity';
comment on column public.alarms.acknowledged_by is 'class=PII;pii=indirect';
comment on column public.alarms.ack_note is 'class=PHI;free-text-may-contain-pii';

comment on column public.attachments.id is 'class=Internal';
comment on column public.attachments.patient_id is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.attachments.object_path is 'class=Internal';
comment on column public.attachments.original_name is 'class=PHI;free-text-may-contain-pii';
comment on column public.attachments.content_type is 'class=Internal';
comment on column public.attachments.size_bytes is 'class=Internal';
comment on column public.attachments.sha256 is 'class=Internal';
comment on column public.attachments.uploaded_by is 'class=PII;pii=indirect';
comment on column public.attachments.created_at is 'class=Internal';

comment on column public.break_glass_grants.id is 'class=Internal';
comment on column public.break_glass_grants.user_id is 'class=PII;pii=indirect';
comment on column public.break_glass_grants.patient_id is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.break_glass_grants.reason is 'class=PHI;free-text-may-contain-pii';
comment on column public.break_glass_grants.granted_at is 'class=PII;pii=activity';
comment on column public.break_glass_grants.expires_at is 'class=Internal';
comment on column public.break_glass_grants.reviewed_by is 'class=PII;pii=indirect';
comment on column public.break_glass_grants.reviewed_at is 'class=Internal';
comment on column public.break_glass_grants.revoked_at is 'class=Internal';
comment on column public.break_glass_grants.revoked_by is 'class=PII;pii=indirect';
comment on column public.break_glass_grants.review_outcome is 'class=Internal';

comment on column public.privacy_consents.id is 'class=Internal';
comment on column public.privacy_consents.user_id is 'class=PII;pii=indirect';
comment on column public.privacy_consents.notice_version is 'class=Internal';
comment on column public.privacy_consents.accepted_at is 'class=PII;pii=activity';

comment on column public.privacy_requests.id is 'class=Internal';
comment on column public.privacy_requests.user_id is 'class=PII;pii=indirect';
comment on column public.privacy_requests.kind is 'class=Internal';
comment on column public.privacy_requests.status is 'class=Internal';
comment on column public.privacy_requests.requested_at is 'class=PII;pii=activity';
comment on column public.privacy_requests.decided_by is 'class=PII;pii=indirect';
comment on column public.privacy_requests.decided_at is 'class=Internal';
