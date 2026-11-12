---
name: t4593-monitor-the-behaviour-on-endpoint
description: Establish behavioural baselines and anomaly alerting for ACME Clinical users and endpoints (staff logins, data access volume, device traffic) by feeding Vercel, Supabase and application security logs into a SIEM with real-time notification and automated containment.
---

# T4593: Monitor the behaviour on endpoint (NON-CODE)

**Category:** INFRA
**SD Elements:** [T4593](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T4593/)
**Priority:** 7/10 · **Phase:** requirements

**Guidance:** Define baseline behaviour (access times, common actions, IP locations, file access volumes), detect deviations with thresholds or ML, centralise behaviour logs in a SIEM, alert security teams in real time, automatically restrict access on high-risk anomalies, and refine detection over time.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no" (EN: "React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the"))
- Found: the app runs on Vercel and hosted Supabase; the repo already emits the raw signals - structured security events on the `acme.security` logger (`backend/app/core/logging.py`), signed audit events (`public.events`), login history (`public.login_activity_summary` in `0006_auth.sql`), lockouts and `public.system_alerts` (`0004_ops_audit_resilience.sql`).
- Missing: a SIEM / EDR platform, baselining across users and time, real-time paging, and endpoint agents on the staff workstations that use the app - none of which can live in this repository.
- Conclusion: Security operations / platform task. The application supplies logs and simple in-app alerts; behavioural analytics, endpoint monitoring and automated response belong to the organization's SOC tooling. Account suspension can reuse the existing audited deactivation path (`backend/app/routers/staff.py`) when triggered by the SOC.

**Recommended Action:** Security operations: (1) configure Vercel log drains for both projects and a Supabase log drain into the SIEM (e.g. Elastic Security, Splunk, Sentinel); (2) ingest `acme.security` events and periodic `public.events` exports; (3) build baselines per role and ward (login hours, source networks, patients viewed per shift, CSV exports, break-glass use) and alert on deviations; (4) route high-severity alerts to the on-call channel in real time; (5) define a playbook that deactivates the account / revokes sessions through the admin API and opens a review; (6) deploy EDR on clinical workstations; (7) review detection rules quarterly.

**Status:** Documented
