---
name: t2614-verify-database-traffic-is-validated
description: Verify that traffic to ACME Clinical's Supabase PostgreSQL database is restricted, well-formed and protected, and that development/test and production databases are separate Supabase projects isolated from each other.
---

# T2614: Verify database traffic is validated (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2614](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2614/)
**Priority:** 9/10 · **Phase:** testing

**Guidance:** Verify that all database traffic is parsed and validated and that malformed or unexpected traffic is blocked; verify that the network uses secure protocol variants (IPsec, DNSSEC, SBGP); verify that development, testing and production databases are hosted separately and firewalled from each other (at minimum an internal firewall separating dev/test from production).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: the database is hosted Supabase PostgreSQL reached by the Vercel-hosted FastAPI backend (and by the frontend through Supabase's API gateway); the PRD does not describe environments or network topology.
- Missing: control over the network path, protocol inspection and firewalls between the Vercel runtime and Supabase. These are operated by Supabase and Vercel, not by repo code.
- Conclusion: Infrastructure verification. The repo can contribute only indirectly: separate `.env` values per environment (`backend/.env.example` `DATABASE_URL`, `SUPABASE_URL`) so dev/test never points at production, and `sslmode=require` (preferably `verify-full`) in `DATABASE_URL`.

**Recommended Action:** Platform/QA owner checklist: (1) confirm production, staging and development are separate Supabase projects (separate credentials, no shared database) and that Vercel Preview/Development env vars do not reference the production project; (2) in Supabase Dashboard > Database > Network Restrictions, confirm direct Postgres access is limited to allowed CIDRs and test that a connection from an unlisted IP is refused; (3) confirm SSL enforcement is on (Database > SSL Configuration) and that a `sslmode=disable` connection is rejected; (4) confirm the Data API only exposes intended schemas (API settings > Exposed schemas); (5) record that IPsec/DNSSEC/SBGP on the transit network are provider responsibilities and attach Supabase/Vercel compliance evidence.

**Status:** Documented
