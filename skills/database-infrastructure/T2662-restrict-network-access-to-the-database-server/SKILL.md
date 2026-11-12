---
name: t2662-restrict-network-access-to-the-database-server
description: Reduce the attack surface of ACME Clinical's Supabase PostgreSQL by allowing direct database connections only from authorized networks using Supabase Network Restrictions and private connectivity options.
---

# T2662: Restrict network access to the database server (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2662](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2662/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Limit network access to the database server: firewall rules for authorized IPs and ports only, network segmentation, product-specific connectivity limits and cloud private connectivity (e.g. Private Link).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: hosted Supabase PostgreSQL, accessed by a Vercel serverless backend; no self-managed network or firewall.
- Missing: firewall/segmentation control, which exists only in Supabase (and Vercel) project settings.
- Conclusion: Platform configuration. Note a constraint: Vercel serverless functions use dynamic egress IPs unless a static-IP/Secure Compute option is used, so an IP allow-list for the backend needs that option or must rely on the Supavisor pooler plus strong auth and TLS. The frontend never connects to Postgres directly; it uses Supabase HTTPS APIs governed by RLS.

**Recommended Action:** Platform owner: (1) Supabase Dashboard > Database > Network Restrictions: allow only admin CIDRs and the backend's egress range; (2) evaluate Vercel Secure Compute / static IPs for the backend so it can be allow-listed; (3) evaluate Supabase private connectivity (PrivateLink, plan-dependent); (4) keep direct port 5432/6543 access closed to everything else and periodically test from an unlisted IP; (5) never expose the service-role key or `DATABASE_URL` to the frontend.

**Status:** Documented
