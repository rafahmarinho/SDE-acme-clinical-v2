-- 0013_consent_and_restriction.sql - purpose-level consent, consent withdrawal, restriction of processing and
-- accuracy of personal data (skills/privacy T178, T604, T754, T742). Idempotent.
--
--   * public.consent_grants: one row per grant of an OPTIONAL purpose (separate from the privacy-notice
--     acknowledgement in public.privacy_consents). Evidence: purpose, notice version, language, request id,
--     timestamp. Withdrawal sets withdrawn_at (the row is kept as evidence); a new grant is a new row.
--   * public.staff_optional_contacts: the only optional personal data item (alarm-escalation phone number).
--     Rows can only be written while an active grant exists (RLS + has_active_consent) and are deleted on
--     withdrawal (API) and when the account is erased (trigger).
--   * public.processing_restrictions / public.processing_allowed(): administrators restrict secondary
--     processing of a person's data (staff activity reports, statistics, research extracts). Clinical care
--     and the legally required audit trail are not restrictable. The reporting views exclude restricted
--     patients; the API checks processing_allowed() before building reports and extracts.
--   * One active patient per (name, birth year, ward): duplicate active records are refused (T742).

-- ---------------------------------------------------------------------------
-- 1. Purpose-level consent grants (T178/T604)
-- ---------------------------------------------------------------------------
create table if not exists public.consent_grants (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.staff_profiles(user_id) on delete cascade,
  purpose text not null check (purpose ~ '^[a-z][a-z_]{2,39}$'),
  notice_version text not null check (notice_version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
  language text not null check (language ~ '^[a-z]{2}(-[A-Z]{2})?$'),
  request_id text check (request_id is null or request_id ~ '^[A-Za-z0-9-]{8,64}$'),
  granted_at timestamptz not null default now(),
  withdrawn_at timestamptz,
  withdrawal_request_id text check (withdrawal_request_id is null or withdrawal_request_id ~ '^[A-Za-z0-9-]{8,64}$'),
  check (withdrawn_at is null or withdrawn_at >= granted_at)
);
create unique index if not exists consent_grants_one_active
  on public.consent_grants(user_id, purpose) where withdrawn_at is null;
alter table public.consent_grants enable row level security;
alter table public.consent_grants force row level security;

drop policy if exists consent_grants_read on public.consent_grants;
create policy consent_grants_read on public.consent_grants for select to acme_api_rw
  using (user_id = public.current_staff_id());
drop policy if exists consent_grants_insert on public.consent_grants;
create policy consent_grants_insert on public.consent_grants for insert to acme_api_rw
  with check (user_id = public.current_staff_id() and withdrawn_at is null);
drop policy if exists consent_grants_withdraw on public.consent_grants;
create policy consent_grants_withdraw on public.consent_grants for update to acme_api_rw
  using (user_id = public.current_staff_id() and withdrawn_at is null)
  with check (user_id = public.current_staff_id() and withdrawn_at is not null);

grant select, insert on public.consent_grants to acme_api_rw;
grant update (withdrawn_at, withdrawal_request_id) on public.consent_grants to acme_api_rw;

-- Time-of-use check (never a cached flag): is there an active grant of p_purpose for p_user?
create or replace function public.has_active_consent(p_user uuid, p_purpose text) returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select exists (select 1 from public.consent_grants g
                 where g.user_id = p_user and g.purpose = p_purpose and g.withdrawn_at is null)
$$;
revoke execute on function public.has_active_consent(uuid, text) from public;

-- ---------------------------------------------------------------------------
-- 2. Optional personal data gated by consent
-- ---------------------------------------------------------------------------
create table if not exists public.staff_optional_contacts (
  user_id uuid primary key references public.staff_profiles(user_id) on delete cascade,
  escalation_phone text not null check (escalation_phone ~ '^\+[1-9][0-9]{7,14}$'),
  updated_at timestamptz not null default now()
);
alter table public.staff_optional_contacts enable row level security;
alter table public.staff_optional_contacts force row level security;

drop policy if exists optional_contacts_read on public.staff_optional_contacts;
create policy optional_contacts_read on public.staff_optional_contacts for select to acme_api_rw
  using (user_id = public.current_staff_id());
drop policy if exists optional_contacts_insert on public.staff_optional_contacts;
create policy optional_contacts_insert on public.staff_optional_contacts for insert to acme_api_rw
  with check (user_id = public.current_staff_id()
              and public.has_active_consent(user_id, 'escalation_contact'));
drop policy if exists optional_contacts_update on public.staff_optional_contacts;
create policy optional_contacts_update on public.staff_optional_contacts for update to acme_api_rw
  using (user_id = public.current_staff_id())
  with check (user_id = public.current_staff_id()
              and public.has_active_consent(user_id, 'escalation_contact'));
drop policy if exists optional_contacts_delete on public.staff_optional_contacts;
create policy optional_contacts_delete on public.staff_optional_contacts for delete to acme_api_rw
  using (user_id = public.current_staff_id());

grant select, insert, delete on public.staff_optional_contacts to acme_api_rw;
grant update (escalation_phone, updated_at) on public.staff_optional_contacts to acme_api_rw;

-- Erasure / retention pseudonymisation also removes optional data and closes every active grant.
drop policy if exists reset_owner_optional_contacts on public.staff_optional_contacts;
create policy reset_owner_optional_contacts on public.staff_optional_contacts for all to acme_reset_owner
  using (true) with check (false);
drop policy if exists reset_owner_consent_grants on public.consent_grants;
create policy reset_owner_consent_grants on public.consent_grants for all to acme_reset_owner
  using (true) with check (true);
grant select, delete on public.staff_optional_contacts to acme_reset_owner;
grant select, update (withdrawn_at) on public.consent_grants to acme_reset_owner;

create or replace function public.privacy_on_staff_erased() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if new.erased_at is not null and old.erased_at is null then
    delete from public.staff_optional_contacts where user_id = new.user_id;
    update public.consent_grants set withdrawn_at = now() where user_id = new.user_id and withdrawn_at is null;
  end if;
  return new;
end $$;
revoke execute on function public.privacy_on_staff_erased() from public;

drop trigger if exists staff_erased_privacy_cleanup on public.staff_profiles;
create trigger staff_erased_privacy_cleanup after update of erased_at on public.staff_profiles
  for each row execute function public.privacy_on_staff_erased();

-- ---------------------------------------------------------------------------
-- 3. Restriction of processing for secondary purposes (T754)
-- ---------------------------------------------------------------------------
create table if not exists public.processing_restrictions (
  id uuid primary key default gen_random_uuid(),
  subject_type text not null check (subject_type in ('staff', 'patient')),
  subject_id uuid not null,
  activity text not null check (activity in ('staff_activity_report', 'statistics', 'research_extract')),
  basis text not null check (basis in ('objection', 'accuracy_contested', 'unlawful_processing', 'legal_claims')),
  created_by uuid not null references public.staff_profiles(user_id),
  created_at timestamptz not null default now(),
  lifted_by uuid references public.staff_profiles(user_id),
  lifted_at timestamptz,
  check ((lifted_at is null) = (lifted_by is null))
);
create unique index if not exists processing_restrictions_one_active
  on public.processing_restrictions(subject_type, subject_id, activity) where lifted_at is null;
alter table public.processing_restrictions enable row level security;
alter table public.processing_restrictions force row level security;

drop policy if exists restrictions_read on public.processing_restrictions;
create policy restrictions_read on public.processing_restrictions for select to acme_api_rw
  using (public.has_permission('staff:manage')
         or (subject_type = 'staff' and subject_id = public.current_staff_id()));
drop policy if exists restrictions_insert on public.processing_restrictions;
create policy restrictions_insert on public.processing_restrictions for insert to acme_api_rw
  with check (public.has_permission('staff:manage') and created_by = public.current_staff_id() and lifted_at is null);
drop policy if exists restrictions_lift on public.processing_restrictions;
create policy restrictions_lift on public.processing_restrictions for update to acme_api_rw
  using (public.has_permission('staff:manage') and lifted_at is null)
  with check (public.has_permission('staff:manage') and lifted_by = public.current_staff_id());
drop policy if exists reset_owner_restrictions on public.processing_restrictions;
create policy reset_owner_restrictions on public.processing_restrictions for select to acme_reset_owner
  using (true);

grant select, insert on public.processing_restrictions to acme_api_rw;
grant update (lifted_by, lifted_at) on public.processing_restrictions to acme_api_rw;
grant select on public.processing_restrictions to acme_reset_owner;

-- True unless an active restriction forbids p_activity for the subject. Null subjects are allowed (e.g. an
-- alarm without a patient, a system event without an actor).
create or replace function public.processing_allowed(p_subject_type text, p_subject uuid, p_activity text)
returns boolean
language sql stable security definer set search_path = public, pg_temp as $$
  select p_subject is null or not exists (
    select 1 from public.processing_restrictions r
     where r.subject_type = p_subject_type and r.subject_id = p_subject and r.activity = p_activity
       and r.lifted_at is null)
$$;
revoke execute on function public.processing_allowed(text, uuid, text) from public;

-- Secondary-use views exclude patients whose data may not be used for statistics (same columns as 0007).
create or replace view reporting.ward_alarm_daily as
select w.code as ward_code, (date_trunc('day', a.raised_at))::date as day, a.type::text as alarm_type,
       a.priority::text as priority, count(*)::int as alarm_count
  from public.alarms a
  join public.patients p on p.id = a.patient_id
  join public.wards w on w.id = p.ward_id
 where not exists (select 1 from public.processing_restrictions r
                    where r.subject_type = 'patient' and r.subject_id = p.id and r.activity = 'statistics'
                      and r.lifted_at is null)
 group by w.code, (date_trunc('day', a.raised_at))::date, a.type, a.priority
having count(*) >= 5;

create or replace view reporting.ward_vitals_daily as
select w.code as ward_code, (date_trunc('day', r.recorded_at))::date as day, count(*)::int as reading_count,
       round(avg(r.heart_rate))::int as mean_heart_rate, round(avg(r.spo2))::int as mean_spo2,
       round(avg(r.resp_rate))::int as mean_resp_rate
  from public.readings r
  join public.patients p on p.id = r.patient_id
  join public.wards w on w.id = p.ward_id
 where not exists (select 1 from public.processing_restrictions pr
                    where pr.subject_type = 'patient' and pr.subject_id = p.id and pr.activity = 'statistics'
                      and pr.lifted_at is null)
 group by w.code, (date_trunc('day', r.recorded_at))::date
having count(distinct r.patient_id) >= 5;

revoke all on all tables in schema reporting from public, anon, authenticated;
grant select on reporting.ward_alarm_daily, reporting.ward_vitals_daily to acme_reporting, acme_api_rw;

-- ---------------------------------------------------------------------------
-- 4. Accuracy: no duplicate active patient records (T742)
-- ---------------------------------------------------------------------------
create unique index if not exists patients_one_active_identity
  on public.patients (lower(display_name), birth_year, ward_id) where discharged_at is null;

-- ---------------------------------------------------------------------------
-- 5. Grants and ownership
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke execute on function public.has_active_consent(uuid, text), '
            'public.processing_allowed(text, uuid, text), public.privacy_on_staff_erased() from anon, authenticated';
  end if;
end $$;
grant execute on function public.has_active_consent(uuid, text), public.processing_allowed(text, uuid, text)
  to acme_api_rw, acme_reset_owner;

do $$
begin
  alter function public.privacy_on_staff_erased() owner to acme_reset_owner;
  alter view reporting.ward_alarm_daily owner to acme_reset_owner;
  alter view reporting.ward_vitals_daily owner to acme_reset_owner;
exception when insufficient_privilege then
  raise notice 'privacy cleanup trigger / reporting views stay owned by %', current_user;
end $$;

-- ---------------------------------------------------------------------------
-- 6. Data classification labels (keep in sync with docs/security/data-classification.md)
-- ---------------------------------------------------------------------------
comment on column public.consent_grants.id is 'class=Internal';
comment on column public.consent_grants.user_id is 'class=PII;pii=indirect';
comment on column public.consent_grants.purpose is 'class=Internal';
comment on column public.consent_grants.notice_version is 'class=Internal';
comment on column public.consent_grants.language is 'class=Internal';
comment on column public.consent_grants.request_id is 'class=Internal';
comment on column public.consent_grants.granted_at is 'class=PII;pii=activity';
comment on column public.consent_grants.withdrawn_at is 'class=PII;pii=activity';
comment on column public.consent_grants.withdrawal_request_id is 'class=Internal';

comment on column public.staff_optional_contacts.user_id is 'class=PII;pii=indirect';
comment on column public.staff_optional_contacts.escalation_phone is 'class=PII;pii=direct;consent=escalation_contact';
comment on column public.staff_optional_contacts.updated_at is 'class=Internal';

comment on column public.processing_restrictions.id is 'class=Internal';
comment on column public.processing_restrictions.subject_type is 'class=Internal';
comment on column public.processing_restrictions.subject_id is 'class=PII;pii=indirect';
comment on column public.processing_restrictions.activity is 'class=Internal';
comment on column public.processing_restrictions.basis is 'class=Internal';
comment on column public.processing_restrictions.created_by is 'class=PII;pii=indirect';
comment on column public.processing_restrictions.created_at is 'class=Internal';
comment on column public.processing_restrictions.lifted_by is 'class=PII;pii=indirect';
comment on column public.processing_restrictions.lifted_at is 'class=Internal';
