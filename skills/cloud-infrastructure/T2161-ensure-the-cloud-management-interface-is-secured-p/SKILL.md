---
name: t2161-ensure-the-cloud-management-interface-is-secured-p
description: Secure ACME Clinical's cloud management interfaces (Vercel dashboard/CLI/API, Supabase dashboard/CLI/Management API, direct Postgres access) with SSO+MFA, restricted access paths, audit logging and alerting, and periodic testing.
---

# T2161: Ensure the cloud management interface is secured properly (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2161](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/activities/32-T2161/)
**Priority:** 9/10 · **Phase:** activities

**Guidance:** Limit management interfaces to authorized IPs/networks, use a bastion or MFA authentication policy before management login, keep tamper-resistant logs of administrative commands with automated alerting, disable unnecessary management services, use only current secure protocols, and penetration-test management interfaces.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: Management planes are the Vercel dashboard/CLI/REST API and the Supabase dashboard/CLI/Management API, plus direct Postgres connections. These are SaaS interfaces; IP restriction of the dashboards themselves is generally not customer-configurable.
- Missing: Management-plane controls are account/IdP settings.
- Conclusion: Platform/IT control. Note the in-app administrator screens and simulation controls (reset, advance) are application features protected by app authorization, not this CM.

**Recommended Action:**
- Authentication: SSO via the organization IdP with MFA and, where the IdP supports it, conditional access (managed device / corporate network) for Vercel and Supabase logins; this substitutes for a bastion in front of SaaS consoles (see T2286).
- Restrict paths:
  - Direct Postgres: Supabase Network Restrictions allow only VPN/office and CI CIDRs; this is the "dedicated management network".
  - Supabase Data API exposed schemas minimal; no admin RPCs callable by `anon`.
  - Vercel API/CLI tokens: scoped, expiring, per person.
- Logging/alerting: Vercel Audit Log and Supabase Organization Audit Logs drained to a SIEM that administrators cannot modify (separate ownership, immutable storage); alert on owner changes, token creation, env var edits, protection disabled, network restriction changes (see T2370).
- Unnecessary services: disable unused Supabase features (e.g. unused Auth providers, GraphQL if unused, Data API schemas), remove unused Vercel integrations and Git connections.
- Protocols: TLS-only (SSL enforcement on Postgres); no password-only DB access for humans beyond break-glass.
- Testing: include management-plane misconfiguration review (token sprawl, member roles, public previews) in the annual penetration test scope.

**Status:** Documented
