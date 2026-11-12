---
name: t2375-verify-that-log-monitoring-and-configuration-monit
description: Verify that log and configuration monitoring with anomaly alarms are active for ACME Clinical on Vercel and Supabase. Part 2/3 of a shared verification countermeasure tracked with T2306.
---

# T2375: Verify that log monitoring and configuration monitoring are enabled (Cloud) (2/3) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2375](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2375/)
**Priority:** 8/10 · **Phase:** testing

**Guidance:** Verify use of provider log monitoring, that configuration monitoring is enabled, that log metrics and alarms exist for anomalies, and that monitoring agents provide comprehensive performance data.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: Vercel-hosted web and API, hosted Supabase. No monitoring requirements.
- Missing: Verification targets are provider/SIEM settings.
- Conclusion: Manual/operational verification.

**Recommended Action:**
Shares identical guidance with T2306 (1/3) and T2376 (3/3); run the T2306 checklist once and record the same evidence here. Re-run after any change to the Vercel team, Supabase plan, or SIEM alert rules.

**Status:** Documented
