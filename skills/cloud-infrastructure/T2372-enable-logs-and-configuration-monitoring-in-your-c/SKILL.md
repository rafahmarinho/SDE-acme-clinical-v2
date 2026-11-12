---
name: t2372-enable-logs-and-configuration-monitoring-in-your-c
description: Enable log monitoring, configuration monitoring and anomaly alerts for ACME Clinical's Vercel and Supabase environments. Part 3/4 of a shared countermeasure tracked with T2294.
---

# T2372: Enable logs and configuration monitoring in your cloud environment (Cloud) (3/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2372](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2372/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** Use the provider's log monitoring services, enable configuration monitoring, create log metrics and alarms for anomalies, and use monitoring agents inside instances.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel-hosted web and API, hosted Supabase. No monitoring requirements.
- Missing: Monitoring configuration is provider-side; serverless functions have no agent install point.
- Conclusion: Platform/operations control.

**Recommended Action:**
Identical guidance to T2294 (1/4), T2371 (2/4) and T2373 (4/4); track together and use the T2294 checklist. Suggested evidence slice for this part: Vercel monitoring.
- Vercel Observability enabled for both projects; alerts/anomaly notifications configured for API 5xx rate, function errors/timeouts and latency regressions, routed to the on-call channel.
- Vercel Firewall events monitored (spikes in denied/challenged requests) via the Firewall dashboard and the log drain.
- Alert on configuration changes from the team Audit Log/Activity: environment variables, Deployment Protection, domains, Git connection, members.
- In place of host agents: OpenTelemetry tracing from FastAPI (`backend/app/main.py`) and Speed Insights for the frontend.

**Status:** Documented
