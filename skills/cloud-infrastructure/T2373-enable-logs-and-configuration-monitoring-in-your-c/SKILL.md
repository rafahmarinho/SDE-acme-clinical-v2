---
name: t2373-enable-logs-and-configuration-monitoring-in-your-c
description: Enable log monitoring, configuration monitoring and anomaly alerts for ACME Clinical's Vercel and Supabase environments. Part 4/4 of a shared countermeasure tracked with T2294.
---

# T2373: Enable logs and configuration monitoring in your cloud environment (Cloud) (4/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2373](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2373/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** Use the provider's log monitoring services, enable configuration monitoring, create log metrics and alarms for anomalies, and use monitoring agents inside instances.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.) and line 19 "...publicados separadamente na Vercel." (EN: ...published separately on Vercel.))
- Found: Vercel-hosted web and API, hosted Supabase with Realtime. No monitoring requirements.
- Missing: Monitoring configuration is provider-side and SIEM-side.
- Conclusion: Platform/operations control.

**Recommended Action:**
Identical guidance to T2294 (1/4), T2371 (2/4) and T2372 (3/4); track together and use the T2294 checklist. Suggested evidence slice for this part: SIEM metrics, alarm routing and runbooks.
- Each alert from T2294 has an owner, a severity, a notification route (pager/on-call chat/email) and a short runbook.
- Alerts are tested once per quarter (synthetic failed-login burst, forced 5xx in a preview deployment).
- Uptime checks from an external monitor on the frontend and on the API health endpoint; alert on loss of the Supabase Realtime connection for live monitoring screens.
- Dashboard summarising Vercel and Supabase health shared with the team.

**Status:** Documented
