---
name: t2374-verify-that-logging-is-enabled-and-log-files-are-p
description: Verify that ACME Clinical's Vercel and Supabase provider logs are enabled and protected (configuration-change logging, encryption, versioning/backup, sufficient detail). Part 2/2 of a shared verification countermeasure tracked with T2305.
---

# T2374: Verify that logging is enabled and log files are protected (Cloud) (2/2) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2374](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2374/)
**Priority:** 9/10 · **Phase:** testing

**Guidance:** Verify provider logging services are used, configuration changes are logged, each cloud service logs, log files are encrypted, logs are versioned and backed up, and log content is sufficient.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: Vercel-hosted web and API, hosted Supabase. No logging requirements.
- Missing: Verification targets are provider and SIEM settings, not repository code.
- Conclusion: Manual/operational verification.

**Recommended Action:**
This part shares guidance with T2305 (1/2); run the T2305 checklist once and attach the same evidence to both tasks. Key items to re-confirm at each release:
- Vercel Log Drain delivering for both projects; Audit Log/Activity capturing env var, domain and protection changes.
- Supabase Log Explorer retention meets requirement or a Supabase Log Drain is configured; Organization Audit Logs enabled where available.
- Log destination encrypted, versioned/immutable, backed up and access-restricted.
- Log entries include request ID, user ID, action and outcome, and exclude secrets and patient data.

**Status:** Documented
