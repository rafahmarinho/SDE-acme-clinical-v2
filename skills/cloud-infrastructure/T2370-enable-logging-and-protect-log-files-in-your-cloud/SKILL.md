---
name: t2370-enable-logging-and-protect-log-files-in-your-cloud
description: Enable and protect provider-side logs for ACME Clinical, including audit logs of the tooling that changes infrastructure (Vercel/Supabase dashboards, CLI tokens, and Terraform if adopted), with restricted access to the log analysis tool. Part 4/4 of a shared countermeasure.
---

# T2370: Enable logging and protect log files in your cloud environment (Cloud) (4/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2370](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2370/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** Same base guidance as parts 1-3 (provider logging, configuration-change logging, restricted/encrypted/versioned logs with sufficient detail), plus monitoring of Terraform audit logs: ship them to an analysis tool (Terraform Cloud Audit Trails API or Terraform Enterprise log shipping), restrict access to that tool, and review failed runs, policy overrides and potential misuse.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel and hosted Supabase. The PRD does not mention Terraform or any infrastructure-as-code tool.
- Missing: Terraform is not part of this stack today; the equivalent "infrastructure change" audit trails are the Vercel team audit log/Activity, the Supabase Organization Audit Logs, and Git history of `vercel.json` / `supabase/migrations/`.
- Conclusion: Platform/process control. The Terraform-specific section applies only if the organization adopts Terraform (e.g. `vercel/vercel` and `supabase/supabase` providers) to manage these projects.

**Recommended Action:**
This part shares base guidance with T2293 (1/4), T2368 (2/4) and T2369 (3/4); track them together. This part's distinct focus is auditing the change tooling.
- Vercel: export the team Audit Log (Enterprise) or Activity feed to the SIEM; alert on environment variable edits, deployment protection disabled, domain changes, new access tokens and role changes.
- Supabase: enable Organization Audit Logs (Team/Enterprise); alert on Network Restrictions or SSL enforcement changes, API key rotation/creation, member invites and project pause/restore.
- CI/CLI: Vercel and Supabase access tokens used by CI must be scoped, expiring and listed in an inventory; review token usage in the audit logs.
- Git: protect the default branch so changes to `backend/vercel.json`, `frontend/vercel.json` and `supabase/migrations/` require review; Git history becomes the configuration-change log for repo-expressed config.
- If Terraform is adopted: use Terraform Cloud (Business) Audit Trails API or Terraform Enterprise log shipping to the SIEM; restrict SIEM access; review failed runs, policy overrides and attempts to use the wrong workspace.

**Status:** Documented
