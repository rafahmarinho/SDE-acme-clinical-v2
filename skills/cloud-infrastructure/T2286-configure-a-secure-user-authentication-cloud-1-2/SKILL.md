---
name: t2286-configure-a-secure-user-authentication-cloud-1-2
description: Secure authentication of the people and automation that administer ACME Clinical's Vercel team and Supabase organization (enforced MFA/SSO, no shared privileged accounts, strong passwords, scoped and rotated access tokens). Part 1/2 of a shared countermeasure.
---

# T2286: Configure a secure user authentication (Cloud) (1/2) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2286](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2286/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Enforce MFA for privileged users; do not use privileged accounts/keys for daily work; enforce strong passwords with expiry and no reuse; rotate credentials regularly and immediately on exposure; remove unused credentials; one active key per user; prefer temporary keys.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 5 "...Supabase para PostgreSQL, login por e-mail e" (EN: ...Supabase for PostgreSQL, email login and...))
- Found: The cloud consoles are Vercel (team) and Supabase (organization). End-user email/password login uses Supabase Auth and is covered by application authentication CMs.
- Missing: Console MFA/SSO enforcement, console password policy and access-token lifecycle are configured in Vercel/Supabase account and team settings (and the organization IdP), not in code.
- Conclusion: Platform/IT control for cloud console users. Application-user password policy can additionally be expressed in `supabase/config.toml` (`[auth] minimum_password_length`, `password_requirements`) and Supabase Auth settings.

**Recommended Action:**
T2286 and T2359 share identical guidance; track together. This file is the master checklist.
- MFA/SSO:
  - Vercel: enable SAML SSO for the team (Enterprise or Pro add-on) with the organization IdP enforcing MFA, or at minimum enable the team setting that requires two-factor authentication for all members.
  - Supabase: enable "Require MFA" for the organization (paid plans) and/or SSO (Team/Enterprise) for dashboard login.
  - GitHub (deploys from Git): require 2FA for the organization owning the repo.
- No privileged daily use: Vercel Owner and Supabase Owner roles held by 2 named break-glass admins; developers use Developer/Member roles.
- Password policy: delegated to the IdP via SSO (length >= 12, no reuse, breach check). Where SSO is not used, require password manager use plus MFA. Prefer phishing-resistant MFA; "90-day expiry" is set in the IdP only if organization policy requires it (NIST 800-63B discourages forced periodic changes without compromise).
- Tokens/keys:
  - Vercel access tokens: scoped to the team, with expiration; one per person/CI job; revoke on departure.
  - Supabase personal access tokens and Management API tokens: one per person/CI job, rotated at least every 90 days, removed when unused.
  - Supabase project secret/service-role key and DB password: rotate on schedule and on exposure (new API keys support rotation without downtime).
  - Prefer short-lived credentials: Vercel OIDC federation for CI/functions where supported, rather than long-lived tokens.
- App users (for completeness, owned by app CMs): enable leaked password protection, minimum length and complexity in Supabase Auth, and TOTP MFA for administrator and physician roles.

**Status:** Documented
