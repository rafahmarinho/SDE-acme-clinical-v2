---
name: t2293-enable-logging-and-protect-log-files-in-your-cloud
description: Enable provider-native logging for ACME Clinical on Vercel and Supabase, log configuration changes, restrict and protect log access, and retain/back up logs with enough detail for clinical audit. Part 1/4 of a shared countermeasure.
---

# T2293: Enable logging and protect log files in your cloud environment (Cloud) (1/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2293](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2293/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** Use the cloud provider's built-in logging services across all services in use, log changes to cloud resource configuration, restrict log access to authorized personnel, encrypt logs where possible, version and back up logs, and ensure log entries contain enough information for auditing and troubleshooting.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: Use current, stable technology versions and Supabase for PostgreSQL, email login and...))
- Found: Frontend and FastAPI API are deployed as separate Vercel projects; database, Auth, Storage and Realtime are hosted Supabase. The PRD says nothing about logging, log retention or audit.
- Missing: The platform log pipelines (Vercel runtime/build logs, Vercel audit log, Supabase Postgres/Auth/Storage/Realtime/API gateway logs, Supabase org audit log) are not configured from application code; access control, encryption, retention and backup of those logs live in the provider consoles.
- Conclusion: Platform/infrastructure control owned by whoever administers the Vercel team and the Supabase organization. The application-side part (what `backend/app/core/logging.py` emits) is covered by application logging CMs; this CM is about enabling and protecting the provider-side logs.

**Recommended Action:**
This is part 1/4. Parts T2293, T2368, T2369 and T2370 share the same guidance and should be tracked together; part 1/4 carries the expanded wording, so use it as the master checklist for the group.
- Vercel (both projects, `acme-clinical-web` and `acme-clinical-api`):
  - Configure a Log Drain (Team Settings > Log Drains) for runtime, build, edge and firewall logs to a SIEM/log store the organization controls (e.g. Datadog, Better Stack, an S3-compatible bucket). Vercel's built-in runtime log retention is short, so the drain is the system of record.
  - Use a signed drain endpoint (verify the drain's secret/signature header) and HTTPS only.
  - Enable/review the team Audit Log (Enterprise) or at minimum the team Activity feed, which records env var changes, domain changes, member/role changes and deployment protection changes.
  - Restrict who can see logs: grant Viewer/Developer roles rather than Owner; logs are visible to all team members of a project, so keep the team membership minimal.
- Supabase (project `acme-clinical`):
  - Use Logs & Analytics / Log Explorer for Postgres, Auth, Storage, Realtime, PostgREST and Edge logs; note plan-based retention (e.g. Pro 7 days, Team 28 days) and choose a plan or a Log Drain (Team/Enterprise) that meets the retention required.
  - Enable the Organization Audit Logs (Team/Enterprise) to capture dashboard and Management API configuration changes.
  - In Postgres, enable `pgaudit` for DDL/role changes (`pgaudit.log = 'ddl, role'`) via a migration in `supabase/migrations/`; keep `log_statement` off for DML to avoid logging clinical data.
  - Supabase Auth events are in `auth.audit_log_entries`; keep RLS-protected and only readable by service role.
- Protection, encryption and backup: the destination SIEM/bucket must encrypt at rest, have object versioning or immutability (WORM/retention lock), restricted IAM, and a documented retention (e.g. 1 year for audit events).
- Sufficient information: ensure drained entries include timestamp, request ID (`x-vercel-id`), user ID (Supabase `sub`), role, action and outcome; do not log passwords, tokens or patient-identifying payloads.
- Repo config that can express part of this: a `pgaudit` migration in `supabase/migrations/`, the request-ID/structured-log format in `backend/app/core/logging.py`, and optionally Terraform (`vercel/vercel` provider `vercel_log_drain`) for the drain definition.

**Status:** Documented
