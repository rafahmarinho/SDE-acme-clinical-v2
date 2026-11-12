---
name: t2368-enable-logging-and-protect-log-files-in-your-cloud
description: Enable and protect provider-side logs for ACME Clinical's Vercel deployments and hosted Supabase project (configuration-change logging, restricted access, encryption, versioned backups, sufficient detail). Part 2/4 of a shared countermeasure.
---

# T2368: Enable logging and protect log files in your cloud environment (Cloud) (2/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2368](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2368/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** Use the cloud provider's logging services, enable logging of configuration changes and of every cloud service in use, restrict access to logs, encrypt logs where possible, version and back up logs, and include sufficient information in log entries.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.))
- Found: Two Vercel projects (web and API) and one hosted Supabase project providing PostgreSQL, Auth, Storage and Realtime. No logging requirements in the PRD.
- Missing: Provider log pipelines, retention, access control and audit trails are configured in the Vercel and Supabase consoles, not in the repo.
- Conclusion: Platform control owned by the Vercel team and Supabase organization administrators.

**Recommended Action:**
This part shares the same guidance as T2293 (1/4), T2369 (3/4) and T2370 (4/4); track them together and use the T2293 checklist as the master. Suggested evidence slice for this part, so the group can be closed with complete coverage: the Supabase service logs.
- Supabase Log Explorer: confirm Postgres, Auth (`auth` logs and `auth.audit_log_entries`), Storage (uploads/downloads of observation attachments and reports), Realtime (channel joins for live monitoring) and PostgREST/API gateway logs are present and queryable.
- Retention: confirm the plan's retention window meets the organization's audit requirement; if not, configure a Supabase Log Drain to the organization SIEM (encrypted at rest, versioned/immutable bucket).
- Access: only Owner/Administrator org members and a named on-call group may read logs; review the Supabase org member list and project-scoped roles.
- Configuration changes: enable Supabase Organization Audit Logs (Team/Enterprise) and `pgaudit` (DDL/role) through a migration in `supabase/migrations/`.
- Content: verify Auth logs include user ID, IP and action; ensure no service-role key or JWT is logged by Edge Functions or the FastAPI API.

**Status:** Documented
