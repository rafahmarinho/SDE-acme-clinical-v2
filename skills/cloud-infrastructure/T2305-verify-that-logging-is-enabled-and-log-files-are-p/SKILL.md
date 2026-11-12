---
name: t2305-verify-that-logging-is-enabled-and-log-files-are-p
description: Verify that ACME Clinical's Vercel and Supabase provider logs are enabled, capture configuration changes, are encrypted, versioned/backed up, access-restricted and sufficiently detailed. Part 1/2 of a shared verification countermeasure.
---

# T2305: Verify that logging is enabled and log files are protected (Cloud) (1/2) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2305](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2305/)
**Priority:** 9/10 · **Phase:** testing

**Guidance:** Verify provider logging services are used, configuration changes are logged, each cloud service logs, log files are encrypted, logs are versioned and backed up, and log content is sufficient.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: Use current, stable technology versions and Supabase for PostgreSQL, email login and...))
- Found: Vercel-hosted web and API, hosted Supabase. No logging requirements.
- Missing: The items to verify are provider console settings and SIEM configuration; there is no in-repo code path to test.
- Conclusion: Manual/operational verification of the controls set by T2293/T2368/T2369/T2370.

**Recommended Action:**
T2305 and T2374 share the same verification guidance; run one verification and record the evidence against both. Suggested checklist (performed by ops/security with Vercel and Supabase admin access):
- [ ] Vercel: a Log Drain exists for both projects and test events arrive in the SIEM (use the "Test" button on the drain or trigger a request to `/health` on the API).
- [ ] Vercel: changing a non-production env var in a test project appears in the Audit Log/Activity and in the SIEM.
- [ ] Supabase: Log Explorer shows Postgres, Auth, Storage, Realtime and API logs; a failed login appears in Auth logs with user/IP.
- [ ] Supabase: Organization Audit Logs (if plan allows) record a test member-role change; `pgaudit` captures a test DDL in a branch/preview project.
- [ ] SIEM/bucket: encryption at rest enabled, versioning or retention lock enabled, retention period documented, access limited to a named group.
- [ ] Sample of 20 log lines contains timestamp, request ID, user ID, action and outcome, and contains no passwords, JWTs, service-role keys or patient payloads.
- Optional automation: a scheduled job querying the SIEM for "no events from source X in 24h" to detect a broken drain.

**Status:** Documented
