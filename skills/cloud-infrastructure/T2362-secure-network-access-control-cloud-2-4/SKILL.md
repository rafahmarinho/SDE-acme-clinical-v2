---
name: t2362-secure-network-access-control-cloud-2-4
description: Apply least-privilege network access control to ACME Clinical's Supabase database (Network Restrictions, SSL-only, minimal exposed schemas). Part 2/4 of a shared countermeasure tracked with T2289.
---

# T2362: Secure network access control (Cloud) (2/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2362](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2362/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Use the default VPC only for test/dev; least-privilege routing tables and NACLs; per-server firewall rules for required ports only; secure Internet gateways and minimal public IPs.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: Use current, stable technology versions and Supabase for PostgreSQL, email login and...))
- Found: Hosted Supabase PostgreSQL. Supabase does not expose VPC/NACL controls on standard plans.
- Missing: Network controls are Supabase project settings.
- Conclusion: Platform control in the Supabase dashboard.

**Recommended Action:**
Identical guidance to T2289 (1/4), T2363 (3/4) and T2364 (4/4); track together using the T2289 checklist. Suggested evidence slice for this part: Supabase.
- Network Restrictions enabled with an explicit CIDR allowlist; `0.0.0.0/0` removed.
- SSL Enforcement enabled (Database settings) so non-TLS Postgres connections are rejected.
- Separate production and non-production projects (or Branching); production DB credentials only in the Vercel Production environment.
- Exposed schemas limited to `public` (or a dedicated API schema); `supabase/migrations/` enables RLS on every exposed table.
- PrivateLink considered if the organization is on Supabase Enterprise and needs private connectivity.

**Status:** Documented
