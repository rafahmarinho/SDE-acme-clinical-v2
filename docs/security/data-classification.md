# Data classification and retention

ACME Clinical ships with **fictitious** demo data, but the schema, access rules and retention are designed as if it
held real health data. Real deployments fall under health-data and privacy law (for example HIPAA, GDPR or LGPD); the
demo seed must stay fictitious.

The labels below are mirrored as `comment on column ... is 'class=...'` in the migrations
(`supabase/migrations/0007_privacy.sql`). `backend/tests/test_privacy.py` fails when a column of a personal-data table
has no label, or when a PII/PHI column is missing from this document (T313/T314). Add both when you add a column.

## Classes

| Class | Meaning | Examples | Handling |
|---|---|---|---|
| **PHI** | Individually identifiable health information (sensitive) | patient name, vitals, ECG, observations, alarms | RLS: clinical roles with ward access or break-glass; never in logs; de-identified for statistics |
| **PII** | Personal information about staff | name, e-mail, sign-in times and IP | RLS: the person and administrators (`staff:manage`); exportable and erasable |
| **Internal** | Operational data without personal content | roles, monitor metadata, timestamps of system state | authenticated staff |
| **Secret** | Credentials and keys | Supabase service role key, JWT secret, DB password, device secret hashes | environment only (Vercel Sensitive env vars), never in git, logs or the browser |
| **Public** | Safe to publish | product name, health endpoint | none |

## Inventory: database (personal-data tables)

| Data element | Location | Class | Source | Purpose | Retention | Allowed roles |
|---|---|---|---|---|---|---|
| Staff e-mail | `staff_profiles.email` | PII (direct) | administrator invite / Supabase Auth confirmed change | sign-in identifier, audit | until erasure / pseudonymisation | self, admin |
| Staff name | `staff_profiles.full_name` | PII (direct) | administrator, self-service | display, attribution | until erasure / pseudonymisation | self, admin |
| Staff key | `staff_profiles.user_id` | PII (indirect, random UUID) | Supabase Auth | key for clinical attribution | kept (pseudonymous) | self, admin |
| Sign-in history | `staff_profiles.last_login_at`, `staff_profiles.previous_login_at`, `staff_profiles.privacy_notice_accepted_at` | PII (activity) | system | security notice, evidence | cleared on pseudonymisation | self, admin |
| Sign-in IP | `staff_profiles.previous_login_ip`, `staff_profiles.last_login_ip` | PII (online identifier) | system | account-takeover notice | cleared on pseudonymisation | self, admin |
| Notice acknowledgements | `privacy_consents.user_id`, `privacy_consents.accepted_at` | PII | self | evidence of notification | life of the account | self, admin |
| Erasure requests | `privacy_requests.user_id`, `privacy_requests.requested_at`, `privacy_requests.decided_by` | PII | self / admin | data-subject rights | life of the account | self, admin |
| Consent grants (optional purposes) | `consent_grants.user_id`, `consent_grants.granted_at`, `consent_grants.withdrawn_at` | PII | self | evidence of consent and withdrawal (T178/T604) | life of the account; withdrawn on erasure | self only |
| Escalation phone (optional, consent-based) | `staff_optional_contacts.user_id`, `staff_optional_contacts.escalation_phone` | PII (direct) | self, only with an active `escalation_contact` grant | alarm escalation by text message (simulated) | until withdrawal or erasure (deleted immediately) | self only |
| Processing restrictions | `processing_restrictions.subject_id`, `processing_restrictions.created_by`, `processing_restrictions.lifted_by` | PII (indirect) | administrators | restriction of secondary processing (T754) | life of the account | subject (own), admin |
| Patient identity | `patients.display_name` | PHI (direct) | admission (demo seed) | care | until `retention_until` after discharge | clinical roles with ward access |
| Patient key / code | `patients.id`, `patients.pseudonym` | PHI (pseudonymous) | system | linking records without names | as above | clinical roles; biomedical technicians (devices only, no API access) |
| Quasi-identifiers | `patients.birth_year`, `patients.ward_id`, `patients.bed_id`, `patients.admitted_at`, `patients.discharged_at` | PHI (quasi) | admission | care, bed management | as above | clinical roles |
| Vital signs and ECG | `readings.patient_id`, `readings.recorded_at`, `readings.heart_rate`, `readings.spo2`, `readings.resp_rate`, `readings.bp_systolic`, `readings.bp_diastolic`, `readings.ecg` | PHI (linked via pseudonym) | simulated monitors | monitoring | `data_retention_days` (default 365) | clinical roles; Realtime for authorised sessions |
| Alarms | `alarms.patient_id`, `alarms.type`, `alarms.priority`, `alarms.message`, `alarms.raised_at`, `alarms.ack_note` | PHI | Python alarm engine, clinicians | alarm handling | resolved alarms: `data_retention_days` | clinical roles |
| Alarm acknowledgement | `alarms.acknowledged_by`, `alarms.acknowledged_at` | PII | clinicians | clinical audit trail | with the alarm | clinical roles |
| Observations | `observations.patient_id`, `observations.body`, `observations.created_at` | PHI (free text may contain PII) | clinicians | clinical record | with the patient record | clinical roles with ward access |
| Observation author | `observations.author_id` | PII (indirect) | server (token), never client input | attribution | with the patient record (author pseudonymised on erasure) | clinical roles |
| Files | `attachments.patient_id`, `attachments.original_name` | PHI | clinicians | clinical documents | with the patient record | clinical roles |
| File uploader | `attachments.uploaded_by` | PII (indirect) | server | attribution | with the file | clinical roles |
| Emergency access | `break_glass_grants.user_id`, `break_glass_grants.patient_id`, `break_glass_grants.reason`, `break_glass_grants.granted_at`, `break_glass_grants.reviewed_by`, `break_glass_grants.revoked_by` | PHI / PII | clinicians, reviewers | emergency access with review | with the patient record | requester, administrators |

Other tables (`wards`, `beds`, `monitors`, `monitor_assignments`, `maintenance_records`, `alarm_thresholds`,
`simulation_state`, `security_settings`, `role_permissions`) hold **Internal** data; `maintenance_records.performed_by`
and `monitor_assignments.assigned_by` are staff references (PII, indirect). `events` (audit trail) holds identifiers
and enumerated values only (no names, e-mails or clinical text) and is append-only and hash-chained.
`app_sessions` holds session ids, timestamps and a hashed IP (PII, indirect). Secrets live in `private` schema tables
or only as hashes (`monitors.device_secret_hash`).

## Inventory: outside the tables

| Location | Content | Class | Controls |
|---|---|---|---|
| Supabase Storage bucket `clinical-files` | patient documents (PDF, PNG, JPEG) | PHI | private bucket, no browser policies, 60 s signed URLs issued by the API; objects deleted when the patient record is purged (`storage_purge_queue`) |
| Supabase Realtime publication `supabase_realtime` (tables `readings`, `alarms`, `monitors`) | vitals, alarm state, device status keyed by UUID | PHI (pseudonymous) / Internal | RLS applies to Realtime: a session receives only rows of patients it can access (`can_access_patient`) |
| Supabase Auth (`auth.users`) | e-mail, password hash (bcrypt, managed by Supabase), MFA factors | PII / Secret | managed by Supabase; scrubbed and banned on erasure |
| API logs (Vercel) | request ids, routes, status, actor UUID and role | Internal / PII (indirect) | redaction filter removes tokens, passwords, e-mails and free text (`backend/app/core/logging.py`) |
| Browser | Supabase session (access/refresh token), current screen data | Secret / PHI | no PHI in `localStorage`; caches cleared on sign-out |
| Reporting schema (`reporting.ward_alarm_daily`, `reporting.ward_vitals_daily`) | ward/day aggregates | Internal (de-identified) | no identifiers or pseudonyms, groups below 5 suppressed |

## Retention schedule

| Category | Retention | Anchor | Action | Mechanism |
|---|---|---|---|---|
| Readings | `security_settings.data_retention_days` (default 365, 30-3650) | `recorded_at` | delete | `public.run_retention_purge()` |
| Resolved alarms | same | `resolved_at` | delete | same |
| Patient record (identity, observations, readings, alarms, files, break-glass grants) | until `patients.retention_until` after discharge | discharge | delete (cascade) + Storage objects removed | same, plus `drain_storage_queue` in the API |
| Patients on legal hold (`patients.legal_hold`) | until the hold is lifted | - | kept | excluded by the purge |
| Staff accounts | deactivation + `data_retention_days`, or an approved erasure request | `deactivated_at` | pseudonymise (name, e-mail, IPs, sign-in times removed; Auth identity scrubbed and banned) | `pseudonymise_staff()` / `complete_erasure_request()` |
| Audit trail (`events`) | life of the system (legal/security record) | - | kept; contains identifiers only | append-only |

The purge runs **daily at 03:15 UTC** from Supabase `pg_cron` (job `acme-retention-purge`) and on demand from
**Settings > Data retention** (administrators). Every run writes one `purge_log` row with **counts only** (no personal
data) and an audit event.

**Backups.** Supabase daily backups and point-in-time recovery (PITR) keep deleted rows until they age out of the
backup window of the plan (7 days on Pro, configurable up to 28 days with PITR). After a restore, run the purge again
before reopening the system so data deleted since the backup is removed again. Document the window in the operations
runbook (README).

**Third parties.** Supabase and Vercel are processors. No other third party receives copies: all external
integrations are simulated.

## De-identification for secondary use (T545)

Statistics and exports for quality improvement use only the `reporting` views: ward code and day (timestamps
generalised to the day), alarm type/priority counts and mean vitals; no patient UUID, pseudonym, name, birth year or
bed; cells with fewer than 5 alarms (or fewer than 5 distinct patients for vitals) are suppressed. The `acme_reporting`
database role can read only these views. The in-app ward activity report returns counts and durations only.
Re-identification risk: low (aggregates over a ward-day with k >= 5); residual risk from very small wards is accepted
because suppression removes such cells. Patient-identifying views (patient list/detail) are primary care use and are
restricted to clinical roles with ward access. The CSV export of the ward activity report applies the same
suppression (counts below 5 are blank, never the exact value) (T544).

**De-identified research extract (T377).** `GET /v1/reports/research-extract` (administrators with
`settings:manage`, audited with row/subject counts only) is the single path for record-level secondary use
(research, alarm-threshold tuning, training data). It applies Safe Harbor removal (`PHI_DROP` in
`backend/app/services/reports.py`): no patient UUID, `PT-nnnn` pseudonym, name, birth year, bed, monitor id/serial,
timestamps, ECG trace, observation or acknowledgement text, file names or Storage paths. Each patient gets a subject
code from HMAC-SHA256 with a random per-extract key that is discarded, so codes differ between extracts and cannot be
linked back; times are offsets in seconds from the subject's first reading; wards with fewer than 5 distinct patients
are dropped. Patients restricted for `research_extract` or `statistics` are excluded.

## Pseudonymisation (T744)

Patient pseudonyms (`patients.pseudonym`, `PT-nnnn`) are assigned codes, not derived from the identity (no hash of
the name), and the mapping pseudonym -> identity exists only in `public.patients`, protected as a separate trust
zone: forced row-level security (`can_access_patient`: ward assignment or an active, time-boxed break-glass grant,
every use audited by `record_break_glass_use`), no grant to `anon`/`authenticated` (the browser only sees UUID-keyed
Realtime rows without names), no access for `acme_reporting` (views only, no pseudonyms) and no access for
biomedical technicians (no `patient:read`). Staff outside the ward get 404, not a name. Reports, CSV exports, the
research extract, audit events and alerts carry UUIDs or derived codes only, never `display_name`. Staff
pseudonymisation on erasure replaces name and e-mail (`pseudonymise_staff`). Re-identification by a person with ward
access is the intended clinical use; any other re-identification requires break-glass and is reviewed.

## Data quality (T743)

Accuracy is enforced at three layers: strict Pydantic request models (types, lengths, character policies, unknown
fields rejected), database constraints (`not null`, `check`, foreign keys, partial unique indexes such as one active
monitor per bed, canonical unique e-mail), and server-assigned authorship and timestamps (`author_id` from the token,
`created_at default now()`). Staff correct their own name on the Profile page; e-mail changes are confirmed by
Supabase Auth before they take effect. Duplicate records are refused (T742): one active patient per (name, birth
year, ward) (`patients_one_active_identity`, 0013), one patient per bed (`patients.bed_id unique`) and one active
monitor per bed; any unique-constraint violation returns a generic 409 `conflict`, never a 500. Every profile change
is audited with the field names (not the values).
