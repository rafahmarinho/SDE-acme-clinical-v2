---
name: t2615-limit-network-access-by-blocking-connections-from
description: Block connections to ACME Clinical's Supabase PostgreSQL from unknown IP addresses using Supabase Network Restrictions (the managed equivalent of pg_hba.conf rules) combined with per-role database access.
---

# T2615: Limit network access by blocking connections from unknown IP addresses (PostgreSQL) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2615](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2615/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** Use `pg_hba.conf` rules to restrict access by user, database and source IP with secure authentication (`hostssl ... scram-sha-256`) and a final `reject`; complement with firewalls that only allow port 5432 from the application server.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: hosted Supabase PostgreSQL accessed from Vercel.
- Missing: `pg_hba.conf` is managed by Supabase and not editable; IP filtering is exposed as the Network Restrictions feature.
- Conclusion: Platform configuration. Vercel serverless egress IPs are dynamic unless a static-IP/Secure Compute option is used, which affects how tight the allow-list can be. Per-database/per-role scoping is partly achievable in SQL (`revoke connect on database postgres from public; grant connect ... to acme_api;`), but Supabase's own roles must keep access.

**Recommended Action:** Platform owner: (1) Supabase Dashboard > Database > Network Restrictions: add only admin and backend egress CIDRs (IPv4 and IPv6); (2) evaluate Vercel static egress IPs for the backend; (3) enforce SSL so all permitted connections are effectively `hostssl`; (4) verify from an unlisted IP that the connection is refused; (5) review the allow-list periodically.

**Status:** Documented
