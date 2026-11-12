---
name: t2304-verify-that-data-at-rest-is-protected-cloud
description: Verify that ACME Clinical's data at rest in Supabase PostgreSQL and Storage is encrypted, backed up (PITR), governed by a retention policy, and access-restricted.
---

# T2304: Verify that data at rest is protected (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2304](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2304/)
**Priority:** 10/10 · **Phase:** testing

**Guidance:** Verify encryption of managed databases and object stores, versioning of storage services, a lifecycle/retention policy, and restricted access to storage.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "...Supabase para PostgreSQL..." (EN: ...Supabase for PostgreSQL...) and line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.))
- Found: Hosted Supabase Postgres and Storage.
- Missing: Encryption and backup evidence comes from the provider; settings set by T2292/T2366/T2367.
- Conclusion: Manual/operational verification, with automatable access checks.

**Recommended Action:**
Checklist:
- [ ] Supabase at-rest encryption evidence (security docs / SOC 2 report) filed for production.
- [ ] PITR enabled on production; last restore drill date and result recorded.
- [ ] Storage: list buckets and confirm none is public; anonymous `GET` on an object URL returns 400/403; signed URL expires as configured.
- [ ] Versioning: documented as not available in Supabase Storage; immutable-key convention confirmed in code review.
- [ ] Retention policy document exists and the `pg_cron`/API purge job ran successfully in the last cycle.
- [ ] With an `authenticated` JWT of a nurse, attempts to read another ward's files are denied (can be added as a pytest/httpx integration test in `backend/tests`).

**Status:** Documented
