---
name: t2666-protect-data-in-transit-with-tls-database-server
description: Require TLS 1.2 or newer for every remote connection to ACME Clinical's Supabase PostgreSQL database, with no plaintext fallback, using Supabase SSL enforcement and sslmode settings in DATABASE_URL.
---

# T2666: Protect data in transit with TLS (Database Server) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2666](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2666/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** TLS must be required (not just enabled) for all remote database connections, with a minimum of TLS 1.2, and it must not be possible to bypass TLS with a less secure protocol.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: the Vercel-hosted backend connects to hosted Supabase PostgreSQL over the Internet.
- Missing: server-side TLS settings (`ssl`, `ssl_min_protocol_version`, certificates) are managed by Supabase.
- Conclusion: Server-side TLS is a Supabase project setting. Client side is repo config: `backend/.env.example` already shows `DATABASE_URL=...?sslmode=require`; production should use `sslmode=verify-full&sslrootcert=<supabase-ca.crt>` to also authenticate the server. Supabase HTTPS endpoints (`SUPABASE_URL`) are TLS-only.

**Recommended Action:** Platform owner: (1) Supabase Dashboard > Database > SSL Configuration: turn on "Enforce SSL on incoming connections" and download the CA certificate; (2) set Vercel production `DATABASE_URL` with `sslmode=verify-full` and the CA path bundled with the backend; (3) verify a connection with `sslmode=disable` is refused and that `select ssl, version from pg_stat_ssl where pid = pg_backend_pid();` reports `t` and TLSv1.2/1.3.

**Status:** Documented
