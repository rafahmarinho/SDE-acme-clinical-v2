---
name: t2620-protect-data-in-transit-with-tls-postgresql
description: Confirm TLS is enforced for every connection to ACME Clinical's Supabase PostgreSQL (pg_stat_ssl check, SSL enforcement, modern TLS versions) and that the backend connects with sslmode=require or verify-full.
---

# T2620: Protect data in transit with TLS (PostgreSQL) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2620](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2620/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** Verify TLS with `SELECT * FROM pg_stat_ssl;`; enable it with `ssl = on`, `ssl_min_protocol_version = 'TLSv1.3'` and server certificate/key settings in `postgresql.conf`; protect all connections, even internal ones.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"))
- Found: hosted Supabase PostgreSQL.
- Missing: access to `postgresql.conf` and server certificates; Supabase manages these and exposes only an "Enforce SSL" toggle and CA download.
- Conclusion: Server TLS is a Supabase setting; the minimum protocol version is set by Supabase (record what it is; TLS 1.3-only may not be configurable). Client-side config lives in the repo: `DATABASE_URL` in `backend/.env.example` with `sslmode=require`, upgraded to `sslmode=verify-full` with the Supabase CA for production.

**Recommended Action:** Platform owner: (1) enable "Enforce SSL on incoming connections" in Supabase Database settings; (2) run `select pid, ssl, version, cipher from pg_stat_ssl join pg_stat_activity using (pid) where usename = 'acme_api';` and confirm `ssl = t` with TLSv1.2+ (ideally 1.3) for backend sessions; (3) confirm a `sslmode=disable` connection is rejected; (4) set production `DATABASE_URL` to `verify-full`.

**Status:** Documented
