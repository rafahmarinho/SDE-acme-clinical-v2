---
name: t2297-verify-that-cloud-users-and-roles-are-set-up-and-m
description: Verify that ACME Clinical's Vercel and Supabase accounts have current contacts for more than one person, working account recovery, and no inactive users or unused groups/roles.
---

# T2297: Verify that cloud users and roles are set up and maintained (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2297](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2297/)
**Priority:** 10/10 · **Phase:** testing

**Guidance:** Verify current contact information for more than one person, existence of access restoration mechanisms, removal of inactive users and unnecessary group memberships, and removal of unused groups/roles.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel team and Supabase organization.
- Missing: Verification targets account settings maintained per T2285.
- Conclusion: Manual/operational verification.

**Recommended Action:**
Checklist:
- [ ] Vercel and Supabase each have >= 2 Owners and a shared, monitored notification/billing email.
- [ ] Recovery path documented (IdP or recovery codes in password manager) and tested once by a non-primary admin.
- [ ] Member lists compared with HR/IdP roster: no leavers, no members inactive > 90 days.
- [ ] No unused Vercel Access Groups, Supabase project role assignments, stale Supabase projects/branches, or unexpected Postgres login roles.
- [ ] Last quarterly review record present.

**Status:** Documented
