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
