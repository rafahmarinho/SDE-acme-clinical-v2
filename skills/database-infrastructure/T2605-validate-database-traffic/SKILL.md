---
name: t2605-validate-database-traffic
description: Protect ACME Clinical's Supabase PostgreSQL against protocol-level attacks by restricting and encrypting database traffic and by isolating development, testing and production databases in separate Supabase projects.
---

# T2605: Validate database traffic (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2605](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2605/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** Parse and validate database traffic and block anything unexpected; use secure protocol variants (IPsec, DNSSEC, SBGP); separate development, testing and production databases on different servers, each firewalled from the others, or at minimum separate dev/test from production with an internal firewall distinct from the Internet-facing one.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: hosted Supabase PostgreSQL accessed from Vercel deployments; no self-managed network.
- Missing: firewalls, packet inspection and routing between Vercel and Supabase are provider-operated; the repo has no network layer to configure.
- Conclusion: Platform/infrastructure. Repo contributions: one Supabase project per environment wired through environment variables only (`backend/.env.example`, `frontend/.env.example`), and `DATABASE_URL` with `sslmode=require` or `verify-full` (with the Supabase CA certificate) so traffic is always TLS. Application-level input validation (Pydantic, parameterized queries) is handled by code-fix CMs in other domains.

**Recommended Action:** Platform owner: (1) create separate Supabase projects for development, staging and production and configure Vercel environment variables per environment (Production vs Preview vs Development); (2) enable Supabase Network Restrictions on production to permit only required CIDRs (and consider the Supabase IPv4 add-on/dedicated pooler or PrivateLink-style options available on the plan); (3) enable "Enforce SSL on incoming connections"; (4) use the Supavisor pooler connection string from the Vercel backend and the Data API (PostgREST) only for exposed schemas; (5) document that transit-network protocol hardening is the providers' responsibility.

**Status:** Documented
