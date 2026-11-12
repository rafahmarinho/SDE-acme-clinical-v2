---
name: t2663-use-a-secure-authentication-mechanism-for-database
description: Ensure the ACME Clinical FastAPI backend and administrators authenticate to Supabase PostgreSQL over TLS with SCRAM-based credentials that are strong, secret and resistant to brute force and on-path attacks.
---

# T2663: Use a secure authentication mechanism for database connections (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2663](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2663/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** Users and applications must authenticate to the database over a secure protocol that does not reveal credentials and is not subject to brute-force guessing or on-path attacks.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 47 "exemplos de variáveis de ambiente" (EN: "examples of environment variables"))
- Found: hosted Supabase PostgreSQL; the backend connects via `DATABASE_URL` (see `backend/.env.example`).
- Missing: control over the server's authentication methods (`pg_hba.conf`, `password_encryption`) and connection rate limiting, which Supabase manages (SCRAM-SHA-256 and Supavisor pooler).
- Conclusion: Platform setting. Repo contributions: `DATABASE_URL` uses a dedicated non-superuser role and `sslmode=require` (prefer `sslmode=verify-full` with the Supabase CA cert) so SCRAM exchange happens inside TLS; real passwords live only in Vercel environment variables, never in the repo.

**Recommended Action:** Platform owner: (1) confirm Supabase uses SCRAM-SHA-256 for Postgres roles; (2) set a long random password for `postgres` and for `acme_api` and store them in a secrets manager/Vercel env vars; (3) enable SSL enforcement and network restrictions; (4) prefer `verify-full` in production `DATABASE_URL`; (5) rotate DB passwords and Supabase service-role/JWT secrets on staff change or suspected leak.

**Status:** Documented
