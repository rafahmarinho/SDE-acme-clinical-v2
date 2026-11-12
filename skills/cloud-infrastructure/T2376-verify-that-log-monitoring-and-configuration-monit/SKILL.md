---
name: t2376-verify-that-log-monitoring-and-configuration-monit
description: Verify that log and configuration monitoring with anomaly alarms are active for ACME Clinical on Vercel and Supabase. Part 3/3 of a shared verification countermeasure tracked with T2306.
---

# T2376: Verify that log monitoring and configuration monitoring are enabled (Cloud) (3/3) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2376](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2376/)
**Priority:** 8/10 · **Phase:** testing

**Guidance:** Verify use of provider log monitoring, that configuration monitoring is enabled, that log metrics and alarms exist for anomalies, and that monitoring agents provide comprehensive performance data.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel-hosted web and API, hosted Supabase. No monitoring requirements.
- Missing: Verification targets are provider/SIEM settings.
- Conclusion: Manual/operational verification.

**Recommended Action:**
Shares identical guidance with T2306 (1/3) and T2375 (2/3); run the T2306 checklist once and record the same evidence here. Close all three tasks together once every checklist item has evidence (screenshots of alert rules, a fired test alert, and the CI `supabase db lint` run).

**Status:** Documented
