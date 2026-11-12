---
name: t2611-verify-that-typical-database-and-server-activities
description: Verify that ACME Clinical's Supabase PostgreSQL logs startup/shutdown, transactions, SQL statements, configuration changes and data changes with identifying metadata, using Supabase logs and pgaudit.
---

# T2611: Verify that typical database and server activities, along with related metadata, are logged (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2611](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2611/)
**Priority:** 8/10 · **Phase:** testing

**Guidance:** Verify that at minimum startup, shutdown, pause, commit/rollback, default database logging, all SQL commands, configuration changes and data changes are logged, including values, names and IDs for each event.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"))
- Found: hosted Supabase PostgreSQL; the PRD says nothing about database logging.
- Missing: control over server log parameters (`log_statement`, `log_connections`, lifecycle logging), which Supabase manages and surfaces in Logs Explorer.
- Conclusion: Platform verification. Statement/DDL/write auditing can be enabled via pgaudit in a `supabase/migrations/` migration (role-level `pgaudit.log`), but server lifecycle events are only visible in Supabase-managed logs. Logging "values" must be balanced against not writing patient data or secrets into logs.

**Recommended Action:** Testing/platform owner: (1) in Supabase Logs Explorer (Postgres logs), confirm restarts, connections and errors appear with timestamps, role and database; (2) enable pgaudit for `write, ddl, role` on application roles and verify an `insert`/`update` from the backend and a schema migration appear with role, object name and statement; (3) verify config changes made through the Dashboard are recorded in the organization audit log; (4) confirm logs are exported via log drain for retention (T2668); (5) record the gaps that Supabase does not expose (e.g. pause events) as accepted platform limitations.

**Status:** Documented
