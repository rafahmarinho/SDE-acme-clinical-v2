# Logging, audit and error handling

Covers T45, T46, T71, T105, T159, T229, T232, T315, T350, T403, T431, T432, T437, T438, T485, T486.
Code: `backend/app/core/{logging,audit,errors}.py`, `backend/app/services/integrity.py`,
`backend/app/routers/{events,reports}.py`, migration `supabase/migrations/0004_ops_audit_resilience.sql`.
Tests: `backend/tests/test_logging_audit.py`.

## Two streams

| Stream | Where | Content |
|---|---|---|
| Application/security log | JSON lines on stdout → Vercel runtime logs / log drain | `acme.*` loggers; `acme.security` holds security events only |
| Audit trail | `public.events` (append-only, hash-chained, signed) | One row per end-user transaction or security decision |

## Confidential data (T46, T229)

Never logged or audited: passwords, JWTs/refresh tokens, Supabase keys, e-mail addresses, patient
names, vital values, observation/ack note text, break-glass reasons, signed Storage URLs.
Callers pass identifiers and enumerated values only. As defence in depth `redact()` masks values
under sensitive keys (text is removed; booleans/numbers such as `has_note` are kept), Bearer
tokens, JWT-shaped strings, `password=`/`token=` pairs and e-mails, and `RedactingFilter` rewrites
every record on the root handler, capped at 2000 characters. `httpx` request logging is set to
WARNING because Storage URLs carry tokens. Production log level is INFO (tested).

Code review checklist item: no `print()`, no logging of `request.headers`/bodies, audit details
are IDs/enums only. The test suite greps `backend/app` for these patterns.

Manual check (to perform after each demo run): search the Vercel runtime logs of the API for
`eyJ`, `@`, `password`, `service_role` — expected: no matches.

## Security events (T45, T315)

`sec_event()` emits `{ts (UTC, ms), event, outcome, user_id, ip, request_id, method, path, ...}`
with user-supplied values truncated to 200 characters. The request context (source IP from
`x-vercel-forwarded-for`/`x-real-ip`, never the spoofable `X-Forwarded-For`) is captured by
`RequestContextMiddleware`.

| Detection point | Event |
|---|---|
| Invalid/expired token, unknown user (AE) | `authn_failed` |
| Role violation / forced browsing (ACE1–3) | `authz_denied` (+ audit `authz.denied`) |
| Unknown resource (ACE1) | `resource_not_found` |
| Unsupported method (RE2) | `method_not_allowed` |
| Pydantic rejection incl. extra fields (AE10, IE1) | `input_validation_failed` (field names only) |
| Upload rejected / malware (FIO1) | `upload_rejected`, `upload_malware_detected` |
| DB/dependency outage, unhandled exception | `dependency_unavailable`, `unhandled_error` |
| Config tampering, watchdog | `config_integrity_violation`, `watchdog_connection_lost` |
| Oversized/malformed messages, rate limits | `request_rejected` (core/middleware.py) |

Gap: password sign-in, recovery and MFA happen in Supabase Auth from the browser; failed logins
and recovery requests are observed in the Supabase Auth logs (dashboard → Logs → Auth), not here.

## Audit record contents (T71, T232)

Each `public.events` row: DB timestamp (`clock_timestamp()`, UTC timestamptz), `actor_id`,
`actor_role`, `session_id` and `aal` from the verified JWT, `source_ip`, `action`,
`entity_type`/`entity_id`, `outcome` (`success|denied|failure`), `error_code` for failures,
`request_id`, enumerated `details` (≤ 3.5 KB, truncated server-side, DB check 4 KB), `signed_at`
(UTC ms), `key_id`, `signature`. Failed attempts are audited too (e.g. `alarm.ack_rejected` with
`already_acknowledged`, `file.rejected` with the rejection reason, `authz.denied`).

## Non-repudiation (T485, T486)

* Algorithm: **ECDSA P-521 with SHA-512** (`cryptography`), over a canonical JSON payload of all
  fields above (`audit.signed_payload`). Every record is signed, including all non-repudiation
  actions (alarm acknowledgement, observations, thresholds, binding, maintenance, staff changes).
* Key: `AUDIT_SIGNING_KEY` (PEM, Vercel env only). Generate with
  `openssl ecparam -name secp521r1 -genkey -noout | openssl pkcs8 -topk8 -nocrypt`. If unset, a
  deterministic key is derived with HKDF-SHA512 from the server-only JWT secret (logged as a
  warning); set a dedicated key in production. `key_id` = first 16 hex chars of SHA-256 of the
  public key; `GET /v1/events/signing-key` (admin) publishes the PEM public key for offline checks.
* Chain: the DB trigger hash-chains every row (`prev_hash`, `hash`) under an advisory lock; since
  0004 the hash also covers the signature columns, so deletion, reordering or edits are detected.
* Verification: `GET /v1/events/integrity` (admin) runs `verify_event_chain()` and re-verifies the
  signatures of the latest 500 records, returning `first_broken_id` and `invalid_signature_ids`.
* Limitation: the signature is made by the server and attests the authenticated session (user id,
  session id, AAL) — user-held keys are out of scope for this demo.

## Protection (T350)

`public.events` is insert-only for `acme_api` (no UPDATE/DELETE/TRUNCATE grants, revoked again in
0004 for every role incl. `service_role`), and triggers reject UPDATE/DELETE/TRUNCATE for any role
including the owner. RLS: admins read all, others only their own rows. The API has no mutation
route for events. Simulation reset never touches `events`/`system_alerts` and is itself audited.
WORM storage is not available on this stack; tampering by a DB superuser is detected by the hash
chain + signatures.

## Failure handling (T431, T432)

`FAILURE_POLICY` in `core/logging.py` is the catalogue (each entry has a test):

| Failure | Response |
|---|---|
| `audit_insert_failed` (minor event) | buffer in memory (≤ 500), retry on next successful write, admin alert |
| `audit_buffer_full` | oldest buffered event dropped, critical admin alert |
| `critical_audit_failed` | action refused with 503 `audit_unavailable` and rolled back |
| `audit_signing_failed` | as above for critical actions; minor events skipped + alert |
| `log_sink_error` | counted, request continues |
| `alert_store_failed` | critical stdout line only (log-drain alerting) |

Minor events are listed in `audit.MINOR_ACTIONS` (simulation ticks, reads, report generation,
denials, login/logout). Alarm generation therefore continues during an audit outage, while an
alarm acknowledgement is not accepted unaudited. Admin alerts go to `public.system_alerts`
(admin-only RLS) and are listed at `GET /v1/events/alerts` with per-process failure counters.
Vercel functions are stateless: the buffer is best effort; stdout logs are the fallback sink.

## Log reduction and reports (T437, T438)

`GET /v1/reports/audit?hours=&actions=a.b,c.d&actor_id=&outcome=` (admin) returns totals by
action/actor/outcome, suspicious actors (≥ 5 denials/failures), first/last id and the chain
verification result. It is read-only (SELECT ordered by id) and itself audited.
`GET /v1/reports/export.csv?kind=audit_events` exports the rows; CSV cells starting with `= + - @`
are prefixed with `'`. The events screen must render values as text (React escaping).

## Errors (T159, T403)

All errors: `{"error": <catalogued message>, "code": <code>, "request_id": <id>}` (+ `fields`
for 422). Unknown routes, 405, invalid UUIDs, malformed JSON, DB errors and unhandled exceptions
never return SQL, stack traces, library names or paths. DB outages map to 503
`monitoring_unavailable`, lock timeouts/deadlocks to 503 `busy`. Login/recovery messages are
Supabase Auth's generic ones in the SPA. Manual check of the deployed API with DevTools/Burp is
pending for each release. Signed/encrypted detailed errors: not applicable (no remote system
needs details).

## Debug surface (T105)

`FastAPI(debug=False)`, `/docs` and `/openapi.json` only outside production, no test routes, no
`breakpoint()/pdb`, `vercel.json` without `--reload` (tested with `APP_ENV=production`).
