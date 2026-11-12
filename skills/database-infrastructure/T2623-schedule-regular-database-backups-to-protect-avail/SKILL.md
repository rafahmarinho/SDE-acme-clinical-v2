---
name: t2623-schedule-regular-database-backups-to-protect-avail
description: Schedule regular PostgreSQL backups for ACME Clinical using Supabase managed daily backups/PITR, optionally supplemented by scheduled pg_dump with a limited read-only role to encrypted, access-controlled storage.
---

# T2623: Schedule regular database backups to protect availability (PostgreSQL) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2623](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2623/)
**Priority:** 6/10 · **Phase:** deployment

**Guidance:** Use `pg_dump` (or another utility) scheduled with a tool such as crontab for regular backups. Validate restores, use a limited dedicated backup account, protect backup files (permissions, encryption) and keep a DR plan.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"))
- Found: hosted Supabase PostgreSQL; no server where crontab could run, and the app runs on Vercel serverless.
- Missing: a host for scheduled jobs with backup storage; Supabase's managed backups replace self-scheduled `pg_dump` for the primary backup.
- Conclusion: Platform configuration. An optional secondary backup could be a scheduled CI job (e.g. GitHub Actions cron running `supabase db dump`/`pg_dump` with a read-only `acme_backup` role) writing to encrypted storage; that is pipeline/ops configuration, not application code. The PRD's "reiniciar os dados" is a simulation reset, not a backup.

**Recommended Action:** Platform owner: (1) confirm Supabase daily backups are active and retention matches policy; enable PITR if needed; (2) if an off-site copy is required, create a `acme_backup` role with `select` only (no write) and schedule `pg_dump` from a CI runner using a secret-stored connection string with `sslmode=verify-full`; (3) store dumps encrypted with restricted access and lifecycle retention; (4) restore-test regularly.

**Status:** Documented
