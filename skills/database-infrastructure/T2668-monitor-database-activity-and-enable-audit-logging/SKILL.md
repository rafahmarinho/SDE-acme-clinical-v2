---
name: t2668-monitor-database-activity-and-enable-audit-logging
description: Ensure ACME Clinical's Supabase PostgreSQL activity is logged durably, exported off-platform, optionally audited with pgaudit, and monitored with alerts and periodic human review.
---

# T2668: Monitor database activity and enable audit logging (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2668](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2668/)
**Priority:** 5/10 · **Phase:** deployment

**Guidance:** Save database logs to a durable store; move log data off site to prevent tampering and meet retention requirements; consider detailed audit logging (e.g. full query text); establish automated alerting for error conditions and regular human review for suspicious patterns.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 43 "consultar eventos" (EN: "view events"))
- Found: hosted Supabase PostgreSQL. The PRD's "consultar eventos" refers to simulation events shown in the app, not database audit logs.
- Missing: control of the Postgres logging collector and log retention, which Supabase runs (Logs Explorer, retention by plan).
- Conclusion: Platform configuration. Repo contribution: a migration can `create extension if not exists pgaudit;` and set role-level audit for the app role (e.g. `alter role acme_api set pgaudit.log = 'write, ddl';`) if the Supabase plan allows; application audit tables for clinical actions (alarm acknowledgement, observations) are a separate code concern.

**Recommended Action:** Platform owner: (1) review Supabase Logs Explorer (Postgres, Auth, API) and confirm retention for the plan; (2) configure a log drain (Supabase Log Drains, plan-dependent) to an external SIEM/log store for off-site, tamper-resistant retention; (3) enable pgaudit for write/DDL on application roles, avoiding logging of secrets; (4) set alerts on authentication failures, connection spikes and errors; (5) schedule a periodic human review of Postgres/Auth logs.

**Status:** Documented
