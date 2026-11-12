---
name: t2299-verify-that-user-authorization-is-securely-configu
description: Verify that administration of ACME Clinical's Vercel team and Supabase organization is limited to trusted users, uses least-privilege roles, and is granted through groups rather than individual users.
---

# T2299: Verify that user authorization is securely configured (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2299](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2299/)
**Priority:** 10/10 · **Phase:** testing

**Guidance:** Verify IAM administration is restricted to a limited trusted group, least-privilege policies are applied, and policies are attached to groups/roles rather than individuals.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel team and Supabase organization.
- Missing: Verification targets console role assignments set by T2287/T2360.
- Conclusion: Manual/operational verification.

**Recommended Action:**
Checklist:
- [ ] Vercel member list: Owners <= 2 named admins; all others Developer/Viewer; Access Groups used for project access where available.
- [ ] Supabase org members: Owners/Administrators <= 2 named admins; others Developer/Read-only; project-scoped roles used where available.
- [ ] Log in as a Developer-role test account: cannot edit Production env vars (Vercel) and cannot change Network Restrictions/SSL enforcement or invite members (Supabase).
- [ ] Production Sensitive env vars cannot be revealed from the dashboard.
- [ ] Any per-user exception is in the exceptions register with justification and expiry.
- [ ] Postgres: `select rolname from pg_roles where rolcanlogin` shows no unexpected login roles.

**Status:** Documented
