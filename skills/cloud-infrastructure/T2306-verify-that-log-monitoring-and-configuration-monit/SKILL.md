---
name: t2306-verify-that-log-monitoring-and-configuration-monit
description: Verify that log monitoring, configuration monitoring, anomaly metrics/alarms and application-level telemetry are active for ACME Clinical on Vercel and Supabase. Part 1/3 of a shared verification countermeasure.
---

# T2306: Verify that log monitoring and configuration monitoring are enabled (Cloud) (1/3) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2306](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2306/)
**Priority:** 8/10 · **Phase:** testing

**Guidance:** Verify use of provider log monitoring, that configuration monitoring is enabled, that log metrics and alarms exist for anomalies, and that monitoring agents provide comprehensive performance data.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel-hosted web and API, hosted Supabase. No monitoring requirements.
- Missing: The verification targets are provider dashboards, alert rules and the SIEM, not repository code.
- Conclusion: Manual/operational verification of T2294/T2371/T2372/T2373.

**Recommended Action:**
T2306, T2375 and T2376 share identical guidance; perform one verification and attach evidence to all three. Checklist:
- [ ] Vercel Observability enabled on both projects; at least one alert rule (5xx/error rate) fires when a preview deployment returns forced errors.
- [ ] Supabase Reports and Advisors reviewed; `supabase db lint` runs in CI and fails on new critical findings.
- [ ] SIEM receives Vercel and Supabase drains; alert rules exist for failed-login bursts, 401/403 spikes, Storage egress spikes, DB saturation.
- [ ] A test configuration change (e.g. toggling a preview env var, inviting a test member to Supabase) generates an alert or audit entry reviewed by security.
- [ ] Monitoring agents: documented as not applicable (serverless/managed); OpenTelemetry traces from the FastAPI API and frontend Speed Insights are visible.
- [ ] Each alert routes to a named owner and has a runbook.

**Status:** Documented
