---
name: t2298-verify-that-user-authentication-is-securely-config
description: Verify that ACME Clinical's Vercel and Supabase console users authenticate with enforced MFA/SSO, privileged accounts are not used daily, and access tokens are rotated, unique per user and removed when unused.
---

# T2298: Verify that user authentication is securely configured (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2298](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2298/)
**Priority:** 10/10 · **Phase:** testing

**Guidance:** Verify MFA for privileged users, restricted daily use of privileged accounts/keys, strong password policy and expiry, regular credential rotation, no unused credentials, a single active key per user, and use of temporary keys.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel team and Supabase organization administer the deployment.
- Missing: Verification targets console/IdP settings set by T2286/T2359.
- Conclusion: Manual/operational verification.

**Recommended Action:**
Checklist (security reviewer with read access to team/org settings):
- [ ] Vercel: SSO enforced or team 2FA requirement enabled; every member shows 2FA enabled.
- [ ] Supabase: organization MFA requirement enabled (or SSO enforced); every member has MFA.
- [ ] Only the named break-glass admins hold Owner in Vercel and Supabase; their audit log shows no routine deploys.
- [ ] IdP password policy screenshot (length, reuse, breach detection, expiry per org policy).
- [ ] Token inventory: no Vercel/Supabase token older than the rotation period, none without an owner, none unused for 90 days, at most one per person/CI job.
- [ ] CI pipeline uses OIDC/short-lived credentials where supported.
- [ ] Supabase service-role key last rotation date within policy.

**Status:** Documented
