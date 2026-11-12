---
name: t2477-test-the-re-deployment-routines
description: Test recipe exercising ACME Clinical's re-deployment runbook and scripts by rebuilding database, API and web layers into a fresh Supabase branch and Vercel preview, verifying the main flows and recording recovery time.
---

# T2477: Test the re-deployment routines

**Category:** CODE_FIX
**SD Elements:** [T2477](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2477/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "principais, mantenha a implementação objetiva e conclua as páginas e ações descritas."
> (EN: main [flows], keep the implementation objective and complete the described pages and actions.)
> Source: specs/PRD.md, line 51

**What the spec implies (naive approach):**
The PRD asks to check the main flows once. Without repeating the deployment from scratch, broken migration ordering, missing env vars or stale runbook steps are discovered only during an outage.

**Secure Implementation Pattern:**
```yaml
# .github/workflows/redeploy-drill.yml
name: redeploy-drill
on: { schedule: [{ cron: "0 5 1 * *" }], workflow_dispatch: {} }
jobs:
  drill:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: supabase/setup-cli@v1
      - name: Fresh database from migrations + seed
        run: |
          supabase start
          supabase db reset            # replays migrations and seed.sql
          supabase test db             # pgTAP: RLS, classification
      - name: Deploy preview (no --prod)
        env: { VERCEL_TOKEN: "${{ secrets.VERCEL_TOKEN }}" }
        run: |
          start=$(date +%s)
          vercel deploy --cwd backend  --token "$VERCEL_TOKEN" --yes > api_url.txt
          vercel deploy --cwd frontend --token "$VERCEL_TOKEN" --yes > web_url.txt
          echo "elapsed=$(( $(date +%s) - start ))s" >> "$GITHUB_STEP_SUMMARY"
      - name: Smoke-test main flows
        run: pnpm --dir frontend exec playwright test e2e/main-flows.spec.ts
        env: { API_URL: "${{ steps.deploy.outputs.api }}" }
```

**Implementation Guidance:**
- Execute the T2478 runbook into a disposable environment (Supabase local/branch + Vercel preview) monthly and before major releases.
- Verify: migrations apply cleanly, demo seed loads 12 patients and 10 monitors, health endpoint OK, Playwright main flows (login, ward view, acknowledge alarm, simulation advance/reset) pass.
- Test a rollback (`vercel rollback`) and document a Supabase backup/PITR restore drill.
- Record elapsed time and issues found; update README runbook accordingly.
- Reference: SD Elements guidance for T2477.

**Success Criteria:**
- [ ] Redeploy drill workflow succeeds end to end.
- [ ] Main-flow smoke tests pass on the redeployed environment.
- [ ] Rollback and restore drills documented with dates and duration.
- [ ] Recovery time is within the documented target.

**Status:** Applied
