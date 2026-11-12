---
name: t2478-manage-re-deployment-routines
description: Make ACME Clinical re-deployable in reasonable time via a documented README runbook and automated scripts for Supabase migrations/seed, backend and frontend Vercel deployments, env var setup, rollback and backup restore.
---

# T2478: Manage re-deployment routines

**Category:** CODE_FIX
**SD Elements:** [T2478](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2478/)
**Priority:** 6/10 · **Phase:** deployment

**Spec Context:**
> "README com os passos para rodar e publicar a versão web e a API na Vercel. Confira os fluxos"
> (EN: README with the steps to run and publish the web version and the API on Vercel. Check the main)
> Source: specs/PRD.md, line 49

**What the spec implies (naive approach):**
The README will describe a one-time manual deploy through dashboards. Rebuilding after an incident then depends on memory: which env vars, which migration order, which Supabase settings, and how to roll back a broken release.

**Secure Implementation Pattern:**
```bash
# scripts/redeploy.sh  -- idempotent re-deployment (CI or operator)
set -euo pipefail
: "${SUPABASE_PROJECT_REF:?}" "${VERCEL_TOKEN:?}" "${VERCEL_ORG_ID:?}"

echo "1/4 Database migrations"
supabase link --project-ref "$SUPABASE_PROJECT_REF"
supabase db push                        # applies supabase/migrations/*.sql in order
[ "${SEED_DEMO:-false}" = "true" ] && psql "$DATABASE_URL" -f supabase/seed.sql

echo "2/4 Backend API"
VERCEL_PROJECT_ID="$VERCEL_BACKEND_PROJECT_ID" \
  vercel deploy --prod --cwd backend --token "$VERCEL_TOKEN" --yes

echo "3/4 Frontend"
VERCEL_PROJECT_ID="$VERCEL_FRONTEND_PROJECT_ID" \
  vercel deploy --prod --cwd frontend --token "$VERCEL_TOKEN" --yes

echo "4/4 Smoke test"
curl -fsS "$API_BASE_URL/health" && curl -fsS -o /dev/null "$WEB_BASE_URL/"
```

**Implementation Guidance:**
- README "Deploy & re-deploy" runbook: prerequisites (Supabase CLI, Vercel CLI, pnpm, Python), creating the Supabase project, applying migrations, optional demo seed, creating two Vercel projects (`backend/`, `frontend/`), required env vars per project (from `.env.example`, secrets marked Sensitive), domains/CORS, smoke tests.
- Add `scripts/redeploy.sh` (above) and a GitHub Actions workflow running it on tags; tokens from CI secrets, never committed.
- Rollback: `vercel rollback` / promote previous deployment; database: forward-fix migrations, or Supabase PITR restore for data loss.
- Keep all infra-relevant config in repo (`vercel.json` files, migrations, seed) so a fresh environment can be rebuilt from git.
- Record target recovery time and last successful re-deploy test (T2477).
- Reference: SD Elements guidance for T2478.

**Success Criteria:**
- [ ] README runbook enables a new operator to deploy all three layers from scratch.
- [ ] `scripts/redeploy.sh` runs idempotently with no secrets in the repo.
- [ ] Rollback and restore procedures documented.
- [ ] Health endpoint and smoke tests confirm a successful deployment.

**Status:** Applied
