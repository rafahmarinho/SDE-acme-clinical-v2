---
name: t2667-schedule-regular-database-backups-to-protect-avail
description: Ensure ACME Clinical's Supabase PostgreSQL (schema, records, WAL, roles/config) and Storage files are backed up regularly, encrypted, access-restricted and validated by restore tests as part of a documented DR plan.
---

# T2667: Schedule regular database backups to protect availability (Database Server) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2667](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2667/)
**Priority:** 6/10 · **Phase:** deployment

**Guidance:** Regularly back up schema, records, transaction logs, encryption keys and metadata (users, configuration). Validate backups by restoring to a new server, encrypt backups, use a limited dedicated backup account, protect backup files, and keep a documented DR plan (backups, replication).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 45 "continuar salvos após recarregar a aplicação" (EN: "remain saved after reloading the application"))
- Found: hosted Supabase PostgreSQL with persisted data; the PRD's data reset (line 43) is a simulation feature, not a backup.
- Missing: scheduling and storage of database backups, which Supabase performs (daily backups on paid plans, optional PITR via WAL archiving).
- Conclusion: Platform configuration plus DR process. Note that Supabase Storage objects are not included in database backups, and secrets (JWT secret, service-role key, Vercel env vars) must be backed up separately in a secrets manager. Schema is reproducible from `supabase/migrations/`.

**Recommended Action:** Platform owner: (1) choose a Supabase plan with daily backups and enable PITR if the RPO requires it; (2) optionally add an off-platform logical backup (`supabase db dump` / `pg_dump` with a read-only role) to encrypted storage with restricted access; (3) back up Storage buckets separately; (4) keep secrets in a managed vault; (5) test restore to a new project regularly (T2604/T2613).

**Status:** Documented
