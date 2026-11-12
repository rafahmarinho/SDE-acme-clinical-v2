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
