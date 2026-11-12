# Privacy controls

Personal data in ACME Clinical: **staff profiles** (PII) and **patient records** (PHI). Demo data is fictitious, but
every control below is built for real data. Inventory and retention: [data-classification.md](data-classification.md).

| Right / principle | Where | How | Countermeasures |
|---|---|---|---|
| Notice before use | Profile screen (`PrivacyNotice`), `GET /v1/me`, `POST /v1/me/privacy-notice` | Versioned notice (purposes, categories, recipients, retention, rights, legal basis). The checkbox is unchecked by default; the profile cannot be edited until the current version is acknowledged (API returns 409). Bumping `PRIVACY_NOTICE_VERSION` (backend `app/services/privacy.py` and frontend `screens/Profile.tsx`, kept equal by a test) re-prompts everyone. Each acknowledgement is stored in `privacy_consents` (user, version, time) and audited. | T239, T751, T752 |
| Review and correct | Profile screen, `GET/PATCH /v1/me` | All staff personal fields are shown. Name is editable (validated: letters only, 1-120 characters, unknown fields rejected); the e-mail changes through Supabase Auth's confirmation e-mail and is mirrored to the profile by a trigger once confirmed; role and wards are administrator-managed (not personal data). The profile is never cached after sign-out. | T177, T238, T743 |
| Access and portability | Profile > Your data, `POST /v1/me/export` | Requires the current password (verified server-side against Supabase Auth; the verification session is revoked at once). Returns JSON (`acme-clinical-personal-data/v1`) with profile, ward assignments, notice acknowledgements, privacy requests, sessions, references (id + time) to every record the user authored (observations, alarm acknowledgements, maintenance, files) including records of patients no longer visible, emergency-access grants, the user's audit trail and processing information (purposes, recipients, retention, source, automated decisions, transfers, withheld content). `Cache-Control: no-store`, download disposition, audit event without personal data. Only the caller's rows are queried. | T740, T741 |
| Erasure | Profile > Delete my account, `POST /v1/me/erasure-request`; Settings > Account erasure requests | The user re-enters the password and types a confirmation; a pending request is created and audited. **Another administrator** (never the subject) completes it: `public.complete_erasure_request()` pseudonymises the profile (name, e-mail, sign-in times and IPs removed, account deactivated, ward assignments deleted) and the API scrubs the Supabase Auth identity (e-mail replaced, metadata cleared, account banned, so existing refresh tokens stop working). Requests can be rejected with an audit trail. | T179, T240 |
| Storage limitation | Settings > Data retention, `pg_cron` | `public.run_retention_purge()` deletes expired patient records with their files, readings and resolved alarms past the retention period, and pseudonymises long-deactivated staff; legal hold is respected; `purge_log` keeps counts only. | T607, T735 |
| Purpose limitation / de-identification | `reporting` schema | Ward/day aggregates with small-cell suppression (k >= 5); the reporting role cannot read patient-linked rows. | T545, T745 |
| Pseudonymisation | schema | Operational rows reference patients by random UUID; Realtime payloads carry the UUID and vitals only; the browser role has no access to `patients`; biomedical technicians have no patient permission in the API. Patient codes (`PT-0001`) are display codes not derived from identity. | T745 |

## Why clinical records survive an erasure request

Health-record law (for example medical record retention rules, HIPAA 45 CFR 164.530(j), GDPR Art. 17(3)(c)/(b)
exemptions for public health and legal obligations, LGPD Art. 16) requires observations, alarm acknowledgements and
maintenance records to be retained with their attribution. ACME Clinical therefore keeps those rows, but they point to
a pseudonymous profile ("Erased user", `erased-<uuid>@erased.invalid`) whose random UUID cannot be linked back to the
person once the Supabase Auth identity has been scrubbed. The audit trail never contained names or e-mails. This is
stated in the notice and in the confirmation text shown before the request is sent.

## Operating notes

* Erasure requests are visible to administrators with `staff:manage` only; completion requires typing `ERASE`.
* If the Supabase Admin API call fails, the database part is still committed and an
  `privacy.identity_scrub_failed` audit event is written; retry by completing the scrub from the Supabase dashboard
  (Authentication > Users > ban and edit e-mail).
* Data protection impact: export and erasure are high-risk operations, hence password re-entry; failed re-entries are
  audited (`privacy.reauth_failed`) and count towards the Supabase Auth lockout.

## Consent for optional data and its withdrawal (T178, T604)

Necessary processing (work account, sign-in and audit data, clinical records) has a lawful basis other than consent
and is covered by the notice above. Only **optional** items need consent; they are listed in
`CONSENT_PURPOSES` (`backend/app/services/consent.py`) and shown on Profile > Optional uses of your data, each with
its purpose, data categories, retention, third parties and how to withdraw. Toggles start **off**.

| Data item | Necessary / optional | Basis |
|---|---|---|
| Name, work e-mail, role, wards, sign-in times/IP, audit trail | necessary | employment / legal obligation / security |
| Clinical records you author | necessary | provision of care, health-record law |
| Mobile phone for alarm escalation (`staff_optional_contacts.escalation_phone`) | optional | **consent** (`escalation_contact`) |

* Grant: `POST /v1/me/consents` (`purpose`, current `notice_version`); stored in `public.consent_grants` with
  purpose, notice version, language, request id and time; audited as `consent.granted`. Consent is separate from the
  notice acknowledgement. A new purpose or a new notice version needs a new grant.
* Gate: `PUT /v1/me/escalation-contact` returns **409 `consent_required`** without an active grant; the RLS policy
  of `staff_optional_contacts` repeats the check (`public.has_active_consent`) at time of use.
* Withdraw: `DELETE /v1/me/consents?purpose=...` (one toggle, as easy as granting). The grant row is kept with
  `withdrawn_at` as evidence, the phone number is deleted immediately, `consent.withdrawn` is audited. Withdrawal does
  not erase other data; that is the erasure flow. The (simulated) text-message processor holds no copy, so no
  processor notification is needed; a real integration must be told to delete the number.
* Erasure/pseudonymisation closes every active grant and deletes optional data (trigger
  `staff_erased_privacy_cleanup`). The personal-data export includes `consents`, `optional_data` and
  `processing_restrictions`.
* Patient data never relies on consent; these purposes apply to staff only.

## Restriction of processing (T754)

Restrictable activities (secondary uses): `staff_activity_report` (the audit summary report and audit CSV export),
`statistics` (ward activity report, CSV export and `reporting.*` views) and `research_extract` (de-identified
extract). Clinical care screens and the legally required audit trail (`public.events`, integrity verification) are
**not** restrictable. Administrators (`staff:manage`) set or lift a restriction
(`POST`/`DELETE /v1/staff/{user_id}/processing-restrictions`, basis: objection, accuracy contested, unlawful
processing, legal claims), both audited; staff see their own restrictions and ask for one from the Profile page
(`POST /v1/me/processing-restrictions/request`, which alerts administrators). Restricted data stays stored but is
excluded at the query layer (`public.processing_allowed()`); the audit summary reports how many subjects were
excluded. Patient restrictions are recorded by administrators in `public.processing_restrictions` with
`subject_type = 'patient'`.

## Primary and secondary purposes (T544, T377)

* Primary purpose: care on the live screens (ward overview, patient detail, alarms) by clinical roles with ward access.
* Secondary purposes: quality reports and statistics (ward activity report, `reporting.*` views), research, alarm
  threshold tuning and training datasets (research extract). They use only aggregated data with small-cell
  suppression (k >= 5, also in the CSV export) or the de-identified extract (Safe Harbor method; see
  data-classification.md). New secondary views or extracts need a privacy review and a test. No processor performs
  de-identification for ACME Clinical; if one is engaged, give written instructions and record them here.
* Demo and test data (`supabase/seed.sql`) are fictitious; real data is never copied into demo or test environments.
