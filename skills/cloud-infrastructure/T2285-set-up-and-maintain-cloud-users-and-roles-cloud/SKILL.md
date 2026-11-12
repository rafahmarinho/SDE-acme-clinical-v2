---
name: t2285-set-up-and-maintain-cloud-users-and-roles-cloud
description: Maintain ACME Clinical's Vercel team and Supabase organization membership (multiple current contacts, account recovery, removal of inactive users and unused groups/roles).
---

# T2285: Set up and maintain cloud users and roles (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2285](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2285/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Keep contact details current for multiple organization members, enable account recovery mechanisms, remove inactive users, and retire unused groups and roles.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 5 "...Supabase para PostgreSQL..." (EN: ...Supabase for PostgreSQL...))
- Found: Two cloud accounts to administer: a Vercel team and a Supabase organization. (The PRD's "gestão da equipe" (team management, line 27) refers to clinical staff inside the app, which is application code.)
- Missing: Console membership, contacts and recovery options are account settings.
- Conclusion: Platform/IT process control.

**Recommended Action:**
- Contacts: set the Vercel team billing/notification email and Supabase organization billing email to a monitored shared mailbox (e.g. security/ops distribution list), not a single person; ensure at least two Owners in each so security notices and incident emails reach more than one person.
- Recovery: with SSO, account recovery is via the IdP; without SSO, each admin stores MFA recovery codes in the company password manager; document Vercel/Supabase support escalation for owner lock-out.
- Inactive users: quarterly review of Vercel members and Supabase org members; remove anyone who left or has not logged in for 90 days; tie offboarding to IdP deprovisioning (directory sync where available).
- Unused groups/roles: remove unused Vercel Access Groups and Supabase project role assignments; remove unused Postgres roles and stale Supabase projects (e.g. old previews/branches) holding demo or real data.
- Record each review (date, reviewer, changes).

**Status:** Documented
