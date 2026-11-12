# Deployment, re-deployment and recovery

The README has the step-by-step runbook. This page records the routine, its tests and the recovery targets
(T2478/T2477).

## Everything needed to rebuild lives in git

| Item | Location |
|---|---|
| Database schema, roles, RLS, functions, jobs | `supabase/migrations/0001...0007` (applied in order, idempotent where possible) |
| Demo data (fictitious) | `supabase/seed.sql` (12 patients, 10 monitors) |
| API build and routing | `backend/vercel.json`, `backend/api/index.py`, `backend/requirements.txt` (exact pins) |
| Web build and routing | `frontend/vercel.json`, `frontend/package.json` + `pnpm-lock.yaml` |
| Environment variable names | `backend/.env.example`, `frontend/.env.example` (placeholders only; values live in Vercel env vars) |
| CI, audits, secret scanning, drills | `.github/workflows/ci.yml`, `.github/dependabot.yml` |

## Targets

* Recovery time objective (full rebuild into a new Supabase project + two Vercel projects): **60 minutes**.
* Recovery point objective: Supabase daily backup (24 h) or PITR (minutes) when enabled.

## Re-deployment routine (summary)

1. `supabase link --project-ref <ref>` then `supabase db push` (applies pending migrations in order).
2. Optional demo data: `psql "$ADMIN_DATABASE_URL" -f supabase/seed.sql` (never on real environments).
3. Create the `acme_api` login password out of band (`alter role acme_api password ...` in the SQL editor) and put the
   resulting `DATABASE_URL` (with `sslmode=verify-full`) in the backend Vercel project.
4. `vercel deploy --prod --cwd backend` then `vercel deploy --prod --cwd frontend`.
5. Smoke test: `GET <api>/v1/health` returns `{"status":"ok"}`; the web root returns 200; sign in, open the ward
   overview, acknowledge an alarm, advance and reset the simulation.

Rollback: `vercel rollback <previous-deployment-url>` (or "Promote" a previous deployment) for either project; for the
database apply a forward-fix migration, or restore with Supabase PITR/backup for data loss (then re-run the retention
purge, see data-classification.md).

## Drill (tested routine)

The `db-drill` job in `.github/workflows/ci.yml` runs on a schedule (monthly) and on demand: it starts a disposable
local Supabase stack, replays **all migrations and the seed** (`supabase db reset`), checks the seed counts (12 patients,
10 monitors) and that RLS is enabled on every public table, and records the elapsed time in the job summary. The
`deploy` job (manual, `workflow_dispatch`) performs steps 1, 4 and 5 against the target environment using CI secrets
(`SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_REF`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_BACKEND_PROJECT_ID`,
`VERCEL_FRONTEND_PROJECT_ID`, `API_BASE_URL`, `WEB_BASE_URL`), then smoke-tests the result.

Record each drill (date, duration, issues, runbook changes) below; perform a rollback drill and a PITR restore drill at
least once per release cycle.

| Date | Type | Duration | Result / issues | Runbook updated |
|---|---|---|---|---|
| _pending first run_ | rebuild from git | | | |

## Throttling and cost controls (T1362)

In the repository: per-instance token buckets (`backend/app/core/middleware.py`), a shared per-user budget in
PostgreSQL for simulation, reports and uploads (`backend/app/core/ratelimit.py`, migration `0009_rate_limits.sql`),
and Supabase Auth limits in `supabase/config.toml` `[auth.rate_limit]`. Hosted settings an operator must apply and
record here (they cannot be set from this repo):

- Vercel Firewall: a rate-limit rule on the API project (e.g. 300 requests/min per IP on `/v1/*`, 20/min on
  `/v1/auth/*`), action "deny" with 429.
- Vercel Spend Management: a monthly spend limit plus usage notifications for both projects.
- Supabase: usage/billing alerts and the Auth rate limits of the hosted project matching `config.toml`.

| Date | Setting | Value | Applied by |
|---|---|---|---|
| _pending_ | Vercel Firewall rate-limit rule | | |
| _pending_ | Vercel spend limit / usage alerts | | |
| _pending_ | Supabase usage alerts | | |

## Transactional e-mail and messaging (T1386, T2157)

All e-mail is sent by Supabase Auth (invitations, recovery, e-mail change, re-authentication codes and the
"password changed" / "e-mail changed" notifications); the API never builds MIME or SMTP headers and every address is
validated (`EmailStr` + `canonical_email`, CR/LF rejected). Templates (`supabase/templates/*.html`) contain only a
single-use link or code, the anti-phishing statement ("ACME Clinical never asks for your password") and a
confidentiality disclaimer: no passwords, no patient data (tested). One recipient per message. Administrator alerts stay
in-app (`public.system_alerts`) and carry identifiers only (`ALERT_DETAIL_KEYS` in `backend/app/core/audit.py`); a
future e-mail/chat forwarder may send only the alert kind and a link.

Operator checklist (hosted, cannot be done from this repo):

- [ ] Choose a transactional provider that supports TLS, SPF, DKIM and DMARC; create SMTP credentials scoped to sending.
- [ ] Set `SUPABASE_SMTP_HOST`, `SUPABASE_SMTP_USER`, `SUPABASE_SMTP_PASS`, `SUPABASE_SMTP_ADMIN_EMAIL` as CI
      environment secrets (`production` environment) so `supabase config push` applies `[auth.email.smtp]`; or enter
      them in Supabase → Authentication → SMTP Settings. Port 587 (STARTTLS); the provider must refuse plaintext AUTH.
- [ ] DNS for the sending domain: SPF record listing the provider, DKIM keys published, DMARC `p=quarantine` (then
      `reject`) with aggregate reports to the security mailbox.
- [ ] Send a test invitation and verify SPF, DKIM and DMARC alignment pass (message headers); record below.
- [ ] Staff training on phishing / not forwarding clinical data by e-mail, DLP rules and service-desk procedures are
      organisational controls recorded in the ISMS, not in this repo.

| Date | Check | Result | By |
|---|---|---|---|
| _pending_ | SPF / DKIM / DMARC alignment of a test e-mail | | |

## Data location (T2170)

The API functions are pinned to Vercel region `gru1` (São Paulo) in `backend/vercel.json`, matching a Supabase
project in `sa-east-1`, so patient and staff data are processed in Brazil (LGPD). If the deployment serves another
jurisdiction, change both together and record it here. Operator checklist:

- [ ] Privacy officer: confirm the jurisdictions of patients and staff and their localisation rules (LGPD, GDPR, HIPAA...).
- [ ] Create the production Supabase project in the matching region (cannot be changed later); record the region.
- [ ] Vercel: confirm the function region of the API project and where logs / log drains are stored.
- [ ] Review sub-processors (SMTP provider, SIEM, backup storage) for data location.
- [ ] Keep a register of any cross-border transfer (date, recipient, volume, sensitivity) and decide whether
      backups/replicas outside the region are permitted.

| Date | Component | Region / location | Transfer outside region? | Approved by |
|---|---|---|---|---|
| _pending_ | Supabase project | | | |
| _pending_ | Vercel API functions | gru1 (repo default) | | |
| _pending_ | Vercel logs / drains, SMTP, SIEM | | | |

## Request handling offloaded to the platform (T374)

There is no self-managed web server. Vercel's edge terminates TLS, buffers complete requests before invoking a
function and absorbs network-level DDoS; the API keeps body/header/URL limits and rate limits as defence in depth
(`backend/app/core/middleware.py`). Per-request resources are bounded in `backend/vercel.json`
(`maxDuration` 30 s, `memory` 1024 MB). Operator checklist:

- [ ] Vercel Firewall on the API project: rate-limit rules on `/v1/auth/*`, `/v1/monitors/*/assignment`,
      `/v1/files/*` uploads and `/v1/reports/*`, plus a general per-IP limit (see "Throttling and cost controls").
- [ ] WAF custom rules: deny methods other than GET/POST/PUT/PATCH/DELETE/OPTIONS and paths outside `/v1/*`.
- [ ] Attack Challenge Mode playbook documented for incidents.
- [ ] Supabase API and Auth rate limits of the hosted project match `supabase/config.toml`.
- [ ] Controlled load test after each change; record the result in the drill table above.

## Endpoint behaviour monitoring and privileged processes (T4593, T4595)

The application emits the signals (structured `acme.security` events, signed `public.events`, login history,
lockouts, `public.system_alerts`, pgaudit statement logs); behavioural analytics and endpoint protection belong to the
organisation's SOC and IT. Operator checklist:

- [ ] Vercel log drains (both projects) and a Supabase log drain into the SIEM; periodic `public.events` export.
- [ ] Baselines per role and ward (login hours, source networks, patients viewed per shift, CSV exports, research
      extracts, break-glass use) with real-time alerts to the on-call channel.
- [ ] Playbook: deactivate the account / revoke sessions through the admin API (`PATCH /v1/staff/{id}`), open a review.
- [ ] EDR on clinical workstations with process telemetry to the SIEM; OS protections (LSASS PPL, WDAC, exploit
      protection; SELinux/AppArmor on Linux).
- [ ] File Vercel and Supabase SOC 2 / ISO 27001 reports (host hardening, process isolation); restrict Vercel team
      owners and Supabase organisation owners, SSO + MFA required. The API never uses the `postgres` superuser
      (enforced at connection time by `verify_least_privilege`).
- [ ] Review detection rules quarterly.
