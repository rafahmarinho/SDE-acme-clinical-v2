---
name: t2287-configure-a-secure-user-authorization-cloud-1-2
description: Apply least privilege to who can administer ACME Clinical's Vercel team and Supabase organization (few admins, role-based assignment via teams/access groups instead of per-user grants, scoped environment variables). Part 1/2 of a shared countermeasure.
---

# T2287: Configure a secure user authorization (Cloud) (1/2) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2287](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2287/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Restrict IAM administration to a small group of trusted users, apply least privilege to every policy, and attach policies to groups/roles rather than individual users (justify any user-specific policy).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 39 "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador." (EN: loss of connection. Have nurse, physician, biomedical technician and administrator profiles.))
- Found: The PRD's roles (nurse, physician, biomedical technician, administrator) are application roles enforced by RLS and the API; cloud console authorization is not described.
- Missing: Vercel team roles/access groups and Supabase org/project roles are configured in the consoles.
- Conclusion: Platform/IT control for cloud console authorization. Application role authorization is code (RLS in `supabase/migrations/`, checks in `backend/app/core/security.py`) and belongs to access-control CMs; do not confuse an app "administrator" with a cloud console admin.

**Recommended Action:**
T2287 and T2360 share identical guidance; track together. This file is the master checklist.
- Vercel:
  - Owner role: 2 named administrators only (they alone manage members, SSO, billing, tokens).
  - Developers: Developer role (cannot change production env vars or domain settings); reviewers/QA: Viewer.
  - Use Access Groups (Enterprise) to grant project access by group (e.g. "acme-clinical-dev"), not per user; with SSO, map IdP groups to Vercel roles (directory sync).
  - Environment variables scoped: Production secrets only on the API project's Production environment; mark them Sensitive so they cannot be read back from the dashboard.
- Supabase:
  - Organization Owner: 2 named administrators; others Developer or Read-only.
  - Use project-scoped roles (Team/Enterprise) so contributors only see the ACME Clinical project they need.
  - Do not share the service-role key with people; only the API's Vercel environment holds it.
  - Database: avoid creating extra Postgres login roles with broad grants; if a reporting/analytics role is needed, grant SELECT on specific views only, via migration.
- GitHub: branch protection and CODEOWNERS on `supabase/migrations/`, `backend/vercel.json`, `frontend/vercel.json` so infra-relevant changes need admin review.
- Repo config: least-privilege DB grants and roles can be expressed in `supabase/migrations/`; Vercel/Supabase membership optionally via Terraform.

**Status:** Documented
