---
name: t2622-monitor-database-activity-and-enable-audit-logging
description: Enable and monitor PostgreSQL activity logging for ACME Clinical on Supabase, using Supabase-managed Postgres logs and the pgAudit extension for detailed audit records, with log export and review.
---

# T2622: Monitor database activity and enable audit logging (PostgreSQL) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2622](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2622/)
**Priority:** 5/10 · **Phase:** deployment

**Guidance:** PostgreSQL does not log activity by default. Confirm `SHOW logging_collector;` is `on` and `log_directory` is valid in `postgresql.conf`, configure further log settings, and prefer the pgAudit extension when standard logging is not detailed enough.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"))
- Found: hosted Supabase PostgreSQL.
- Missing: `postgresql.conf`, `logging_collector` and `log_directory` are Supabase-managed; logs are surfaced in the Logs Explorer instead of files.
- Conclusion: Platform configuration, with pgAudit as the part expressible in the repo: a migration in `supabase/migrations/` such as `create extension if not exists pgaudit;` followed by `alter role acme_api set pgaudit.log to 'write, ddl';` (Supabase supports pgaudit; avoid `all`/`read` on high-volume reading tables to control log volume and avoid leaking patient values).

**Recommended Action:** Platform owner: (1) confirm Postgres logs are visible in Supabase Logs Explorer and note retention for the plan; (2) enable pgaudit for application and admin roles at an appropriate level; (3) export logs with a log drain to an external store; (4) configure alerts and periodic review (see T2668).

**Status:** Documented
