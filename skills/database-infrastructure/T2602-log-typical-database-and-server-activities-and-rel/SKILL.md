---
name: t2602-log-typical-database-and-server-activities-and-rel
description: Log ACME Clinical's Supabase PostgreSQL server lifecycle, transactions, SQL statements, configuration changes and data changes with identifying metadata, using Supabase-managed Postgres logs, pgaudit and log drains, complementing the application's signed events table.
---

# T2602: Log typical database and server activities and related metadata (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2602](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T2602/)
**Priority:** 8/10 · **Phase:** development

**Guidance:** At minimum log database/server startup, shutdown and pause, transaction commit/rollback, default database logging, all SQL commands, configuration changes and data changes, and record metadata for each event (values, names, IDs) so it can be traced to its origin.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, e-mail and [password] login"))
- Found: hosted Supabase PostgreSQL; the PRD does not mention database logging. The repo already records application-level data changes in the append-only, hash-chained and signed `public.events` table (`supabase/migrations/0001_schema.sql`, `0004_ops_audit_resilience.sql`, `backend/app/core/audit.py`).
- Missing: control over server parameters (`log_statement`, `log_connections`, `log_disconnections`, lifecycle logging) and log storage, which Supabase manages and exposes through Logs Explorer and log drains.
- Conclusion: Platform/infrastructure task. One part can be expressed in the repo: a migration enabling the `pgaudit` extension and setting role-level `pgaudit.log = 'write, ddl, role'` for `acme_api`, `acme_api_rw` and `acme_reset_owner`. Server start/stop/pause and Dashboard configuration changes are only visible in Supabase-managed logs and the organization audit log. Full "values" logging must be balanced against not writing patient data or secrets into logs (T46).

**Recommended Action:** Database/platform owner: (1) enable pgaudit via a `supabase/migrations/` migration for the application roles (write, DDL, role changes; avoid `read` to keep PHI volume out of logs); (2) confirm Postgres logs in Supabase Logs Explorer show restarts, connections, errors and statements with timestamp, role, database and application name (set `application_name=acme-api` in `DATABASE_URL`); (3) configure a Supabase log drain to the organization SIEM with retention matching `docs/security/logging-audit.md`; (4) keep the organization audit log enabled for Dashboard configuration changes; (5) document accepted gaps (e.g. pause events on managed instances) in `docs/security/logging-audit.md`.

**Status:** Documented
