---
name: t2613-verify-best-practices-for-data-restoring-operation
description: Verify that ACME Clinical's Supabase restore procedures are regularly tested, backed by a restoration checklist, monitored for backup anomalies and shared with responsible personnel.
---

# T2613: Verify best practices for data-restoring operations are followed (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2613](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2613/)
**Priority:** 7/10 · **Phase:** testing

**Guidance:** Verify recovery procedures are tested regularly, a comprehensive restoration checklist exists, backup verification tools check size and integrity with immediate alerts on anomalies, and the restoration plan is shared with the people in charge during a failure.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 43 "reiniciar os dados" (EN: "reset the data"))
- Found: hosted Supabase PostgreSQL; the reset is a simulation feature and not evidence of a restore capability.
- Missing: restore tests and backup monitoring are operational activities on Supabase, not application behaviour.
- Conclusion: Process verification. Evidence can live in the repo as documentation (restore checklist in the README requested at line 47) but the test itself is operational.

**Recommended Action:** QA/ops owner: (1) confirm a dated record of the last restore rehearsal (restore to a new Supabase project) and its duration against the RTO; (2) confirm the restoration checklist exists and covers database, Auth, Storage, secrets and Vercel env vars; (3) confirm someone is alerted when a Supabase backup fails or an off-site dump is abnormally small; (4) confirm the on-call team knows where the runbook is.

**Status:** Documented
