---
name: t2371-enable-logs-and-configuration-monitoring-in-your-c
description: Enable log monitoring, configuration monitoring and anomaly alerts for ACME Clinical's Vercel and Supabase environments. Part 2/4 of a shared countermeasure tracked with T2294.
---

# T2371: Enable logs and configuration monitoring in your cloud environment (Cloud) (2/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2371](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2371/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** Use the provider's log monitoring services, enable configuration monitoring, create log metrics and alarms for anomalies, and use monitoring agents inside instances.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: Vercel-hosted web and API, hosted Supabase. No monitoring requirements.
- Missing: Monitoring and alerting live in Vercel Observability, Supabase Reports/Advisors and the SIEM; no instances exist for agents.
- Conclusion: Platform/operations control.

**Recommended Action:**
Identical guidance to T2294 (1/4), T2372 (3/4) and T2373 (4/4); track together and use the T2294 checklist. Suggested evidence slice for this part: Supabase monitoring.
- Supabase Reports reviewed for Database (CPU, connections, disk), Auth (sign-ins, errors), Storage and Realtime; thresholds documented.
- Security Advisor findings are zero or accepted; `supabase db lint` runs in CI for `supabase/migrations/`.
- SIEM alerts exist for: failed-login bursts, password-reset bursts, Realtime connection spikes, unusual Storage egress, DB connection saturation.
- Alerts on Supabase configuration changes (Network Restrictions, SSL enforcement, API keys, members) from Organization Audit Logs.

**Status:** Documented
