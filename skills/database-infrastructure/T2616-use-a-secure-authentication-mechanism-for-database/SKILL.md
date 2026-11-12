---
name: t2616-use-a-secure-authentication-mechanism-for-database
description: Ensure ACME Clinical's Supabase PostgreSQL uses SCRAM-SHA-256 (never trust, password, ident or md5) for role authentication and that the postgres admin account is not used remotely by the application.
---

# T2616: Use a secure authentication mechanism for database connections (PostgreSQL) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2616](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2616/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** In `pg_hba.conf`, do not use `trust`, `password` or `ident`; prefer `scram-sha-256` over `md5` (set `password_encryption` first and reset passwords if migrating); do not allow remote access to the administration account unless required.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"))
- Found: hosted Supabase PostgreSQL.
- Missing: `pg_hba.conf` and `postgresql.conf` are not editable on Supabase; the platform manages host-based authentication.
- Conclusion: Platform setting. Repo contributions: roles created in `supabase/migrations/` (e.g. `acme_api`) get SCRAM-hashed passwords set out-of-band (never a literal password in a migration), and the backend uses `acme_api` in `DATABASE_URL`, not `postgres`.

**Recommended Action:** Platform owner: (1) verify `show password_encryption;` returns `scram-sha-256` and `select rolname from pg_authid where rolpassword like 'md5%';` returns no rows (reset any md5 passwords); (2) restrict remote use of `postgres` to administrators via Network Restrictions and keep its password in a vault; (3) use the Supabase pooler endpoint for the backend; (4) document that `pg_hba.conf` is Supabase-managed.

**Status:** Documented
