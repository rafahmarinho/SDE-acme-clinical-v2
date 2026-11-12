# ACME Clinical

Simulated ward patient-monitoring system: fictitious patients, simulated monitors (heart rate, SpO2, respiration,
blood pressure, synthetic ECG), alarms, devices, alarm-threshold settings, reports, team management and a simulation
area. English is the default language. The code is built as if it handled real health data (see [Security](#security)).

| Part | Stack | Deploy |
|------|-------|--------|
| `backend/` | Python 3.12+, FastAPI, Pydantic (readings, alarms and reports generated in Python) | Vercel (Python functions) |
| `frontend/` | React, Vite, TypeScript, pnpm | Vercel (static, CDN) |
| `supabase/` | PostgreSQL migrations (RLS, roles, functions), seed data; Supabase Auth, Storage, Realtime | Supabase |

Roles: nurse, physician, biomedical technician, administrator (navigation adapts to the role). Demo data: 12
fictitious patients, 10 simulated monitors.

## 1. Prerequisites

* Python 3.12+ and `pip`; Node.js 20.19+ (22 LTS recommended) and pnpm 10 (`corepack enable`).
* [Supabase CLI](https://supabase.com/docs/guides/cli) and a Supabase account; [Vercel CLI](https://vercel.com/docs/cli)
  (`npm i -g vercel`) and a Vercel account.
* `psql` (PostgreSQL client) for the seed and role password.

## 2. Supabase setup

1. Create a project (choose the region you will also use for the API functions, e.g. `us-east-1`).
2. Link and apply the migrations **in order** (`0001` ... `0007`):
   ```bash
   supabase login
   supabase link --project-ref <project-ref>
   supabase db push
   ```
3. Demo data (fictitious only, never on a real environment):
   `psql "$ADMIN_DATABASE_URL" -f supabase/seed.sql` (`ADMIN_DATABASE_URL` = the project's `postgres` connection string
   from *Project Settings > Database*, with `?sslmode=verify-full&sslrootcert=system`).
4. Give the least-privilege API role a strong password (SQL editor, run once, never commit it):
   `alter role acme_api with password '<generated: python -c "import secrets;print(secrets.token_urlsafe(32))">';`
5. Authentication (*Authentication > Providers / Settings*): e-mail provider on, sign-ups **disabled** (staff are
   invited by administrators), "Secure email change" and "Secure password change" on, minimum password length 12,
   TOTP MFA enabled. Register the password-verification hook from `0006_auth.sql` under *Auth Hooks*.
   Set *URL Configuration* site URL and redirect URLs to your web domain (`https://<web>.vercel.app/reset-password`).
6. Extensions: enable `pg_cron` (*Database > Extensions*) **before** `supabase db push` so the daily retention purge
   and the watchdog jobs are scheduled (re-run `supabase db push` or the `0007` migration otherwise).
7. Backups: enable PITR for real data (*Database > Backups*); note the retention window in
   [docs/security/data-classification.md](docs/security/data-classification.md).
8. Demo staff accounts (one per role, random passwords printed once):
   `cd backend && ADMIN_DATABASE_URL=... python -m app.cli create-demo-staff example.org --allow-demo`, then
   `python -m app.cli provision-monitor-secrets`.

## 3. Run locally

```bash
# API
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                              # fill in values; APP_ENV=development locally
uvicorn app.main:app --reload --port 8000         # docs at http://localhost:8000/docs (development only)
python -m pytest -q                               # tests (no database needed)

# Web
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env.local                        # VITE_API_BASE_URL=http://localhost:8000 for local runs
pnpm dev                                          # http://localhost:5173
pnpm exec tsc -b && pnpm test -- --run            # type check + tests
```

`APP_ENV` defaults to `production` when unset (docs off, HTTPS-only URLs). A local Supabase stack
(`supabase start`) can be used with `APP_ENV=development` and `http://localhost` URLs.

## 4. Publish on Vercel (two projects)

**API project** (root directory `backend/`, framework "Other"; `backend/vercel.json` routes everything to
`api/index.py`):

```bash
cd backend && vercel link        # create project "acme-clinical-api"
vercel env add APP_ENV production            # value: production
vercel env add SUPABASE_URL production
vercel env add SUPABASE_ANON_KEY production
vercel env add SUPABASE_SERVICE_ROLE_KEY production --sensitive
vercel env add SUPABASE_JWT_SECRET production --sensitive
vercel env add DATABASE_URL production --sensitive    # postgresql://acme_api:<pw>@<host>:5432/postgres?sslmode=verify-full&sslrootcert=system
vercel env add CORS_ALLOWED_ORIGINS production       # https://<web>.vercel.app
vercel deploy --prod
```
Set *Settings > Functions > Function Region* to the Supabase project's region.

**Web project** (root directory `frontend/`, framework "Vite", install command `pnpm install --frozen-lockfile`,
build `pnpm build`, output `dist`):

```bash
cd frontend && vercel link       # create project "acme-clinical-web"
vercel env add VITE_SUPABASE_URL production
vercel env add VITE_SUPABASE_ANON_KEY production
vercel env add VITE_API_BASE_URL production          # https://<api>.vercel.app
vercel deploy --prod
```
Replace the placeholder hosts (`project-ref.supabase.co`, `acme-clinical-api.vercel.app`) in the
Content-Security-Policy of `frontend/vercel.json` with your Supabase and API hosts before deploying.

**Smoke test:** `curl -fsS https://<api>.vercel.app/v1/health` returns `{"status":"ok"}`; open the web URL, sign in,
open the ward overview, acknowledge an alarm, advance and reset the simulation, reload and check the results persist.

## 5. Re-deploy, rollback and restore (runbook)

| Situation | Steps |
|---|---|
| New release | merge to `main` (CI green), `supabase db push`, `vercel deploy --prod` in `backend/` then `frontend/`, smoke test. The manual `deploy` job in `.github/workflows/ci.yml` does exactly this with CI secrets. |
| Broken web or API release | `vercel rollback` (or *Deployments > Promote* a previous deployment) for the affected project; smoke test. |
| Broken migration | write a forward-fix migration (`0008_...sql`) and `supabase db push`; never edit applied migrations. |
| Data loss / corruption | Supabase *Database > Backups* (daily) or PITR restore to a point in time; then run *Settings > Data retention > Run retention purge* so data deleted since the backup is removed again; smoke test. |
| Rebuild from scratch | sections 2 and 4 in a new Supabase project and two new Vercel projects (target: 60 minutes). |
| Secret exposure | rotate in Supabase (*API > JWT secret / service role key*, `alter role acme_api password ...`), update the Vercel env vars, redeploy both projects. |

The re-deployment drill (`db-drill` job: fresh database from all migrations + seed, RLS and seed checks) runs monthly
in CI; record drills in [docs/security/deployment.md](docs/security/deployment.md).

## Security

Security documentation index: [docs/security/README.md](docs/security/README.md).

* Architecture and trust boundaries (three layers, keys per layer): [architecture.md](docs/security/architecture.md)
* Data classification, inventory, retention schedule, backups: [data-classification.md](docs/security/data-classification.md)
* Privacy (notice, review/correct, export, erasure, retention, de-identification): [privacy.md](docs/security/privacy.md)
* Secure configuration (every setting, defaults, crypto inventory, TLS, dependencies, licenses): [secure-config.md](docs/security/secure-config.md)
* Deployment, re-deployment drills and recovery targets: [deployment.md](docs/security/deployment.md)
* Authentication: [authentication.md](docs/security/authentication.md) · Authorization and roles: [authorization.md](docs/security/authorization.md) · Sessions: [sessions.md](docs/security/sessions.md)
* Input validation: [input-validation.md](docs/security/input-validation.md) · Web front end: [web-frontend.md](docs/security/web-frontend.md) · Files: [file-handling.md](docs/security/file-handling.md)
* Logging and audit: [logging-audit.md](docs/security/logging-audit.md) · Clinical safety and resilience: [clinical-safety.md](docs/security/clinical-safety.md)

Summary:

* **Roles and access:** nurse, physician, biomedical technician, administrator; permissions are enforced by the API
  and mirrored by row-level security in Postgres. Emergency ("break glass") access is time-boxed and reviewed.
* **Authentication:** Supabase Auth e-mail/password, password recovery, lockout, MFA for administrators, idle and
  absolute session timeouts.
* **Data handled:** staff PII and patient PHI (fictitious in the demo). TLS in transit everywhere (`sslmode=verify-full`
  to Postgres), encryption at rest by Supabase, RLS forced on every table, private Storage bucket with signed URLs.
* **Secrets:** only in Vercel environment variables (Sensitive); `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`
  and `DATABASE_URL` are backend-only. `.env` files are git-ignored; CI runs gitleaks.
* **Logging and audit:** append-only, hash-chained `events` table; logs exclude passwords, tokens, e-mails and
  clinical text.
* **Data sanitisation:** daily retention purge, staff erasure requests, simulation reset (demo data only).
* **Supply chain:** exact pins, lockfile, `pip-audit`/`pnpm audit`, Dependabot, license allow-list.
* **Insecure demo settings — change before real use:** demo staff accounts from `create-demo-staff` (delete or rotate),
  the fictitious seed (`supabase/seed.sql`, never load into a real project), `APP_ENV=development` or
  `ENABLE_DOCS=true` (never in production), placeholder hosts in `frontend/vercel.json`, the simulation reset
  (administrators only; it deletes readings, alarms and observations).
* **Reporting vulnerabilities:** contact the security team privately (security@acme-clinical.example); do not open
  public issues for vulnerabilities.

SD Elements project **ACME Clinical v2** (ID 32); countermeasure index in [`AGENTS.md`](./AGENTS.md).
