---
name: t2294-enable-logs-and-configuration-monitoring-in-your-c
description: Enable log monitoring, configuration monitoring and anomaly alerts for ACME Clinical's Vercel deployments and hosted Supabase project; monitoring agents inside instances are replaced by platform observability because the stack is serverless/managed. Part 1/4 of a shared countermeasure.
---

# T2294: Enable logs and configuration monitoring in your cloud environment (Cloud) (1/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2294](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2294/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** Use the provider's log monitoring services, enable configuration monitoring for cloud resources, create log metrics and alarms that notify on anomalies, and use monitoring agents inside instances for deeper performance data.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: Use current, stable technology versions and Supabase for PostgreSQL, email login and...))
- Found: Serverless Vercel functions (Python FastAPI) and static frontend; managed Supabase. No monitoring requirements in the PRD.
- Missing: There are no customer-managed instances to install agents on; monitoring, metrics and alerting are configured in Vercel Observability, Supabase Reports/Advisors and the organization SIEM.
- Conclusion: Platform/operations control. Note: the clinical alarms in the PRD (`backend/app/services/alarms.py`) are product features, not infrastructure monitoring, and are out of scope here.

**Recommended Action:**
This is part 1/4. Parts T2294, T2371, T2372 and T2373 have identical guidance and should be tracked together; this file holds the master checklist.
- Log monitoring:
  - Vercel: enable Observability (Observability Plus for longer retention and queries) on both projects; configure alerts/anomaly notifications for 5xx rate, function duration, function errors and firewall spikes; use the Log Drain (see T2293) to feed SIEM alert rules.
  - Supabase: use Reports (API, Auth, Database, Storage, Realtime) and Log Explorer; feed logs via Supabase Log Drain to the SIEM for alerting.
- Configuration monitoring:
  - Run Supabase Security and Performance Advisors on every migration (Dashboard > Advisors, or `supabase db lint` in CI) and alert on new findings such as tables without RLS.
  - Alert from audit logs on Vercel env var edits, Deployment Protection disabled, domain changes; and Supabase Network Restrictions/SSL enforcement changes, API key creation, member/role changes.
- Metrics and alarms to create in the SIEM: failed logins per minute (Supabase Auth), password-reset bursts, 401/403 spikes on the API, Realtime connection spikes, sudden Storage download volume, DB CPU/connection saturation.
- Agents: not applicable (no VMs). Equivalent depth: OpenTelemetry instrumentation in `backend/app/main.py` exported to the observability backend, and Vercel Speed Insights/Web Analytics for the frontend.
- Repo config: CI step running `supabase db lint`; OpenTelemetry settings via env vars in `backend/.env.example`.

**Status:** Documented
