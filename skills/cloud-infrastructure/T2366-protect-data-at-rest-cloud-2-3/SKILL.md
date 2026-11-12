---
name: t2366-protect-data-at-rest-cloud-2-3
description: Protect ACME Clinical's data at rest in Supabase PostgreSQL (provider encryption, PITR/backups, retention). Part 2/3 of a shared countermeasure tracked with T2292.
---

# T2366: Protect data at rest (Cloud) (2/3) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2366](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2366/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Encrypt sensitive volumes, managed database instances and object stores; enable versioning where possible; define a lifecycle/retention policy; restrict access to storage services.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 45 "devem aparecer nas telas e continuar salvos após recarregar a aplicação." (EN: must appear on screen and remain saved after reloading the application.) and line 5 "...Supabase para PostgreSQL..." (EN: ...Supabase for PostgreSQL...))
- Found: Persistent clinical data in hosted Supabase PostgreSQL.
- Missing: Database encryption and backups are Supabase-managed.
- Conclusion: Platform control in the Supabase dashboard.

**Recommended Action:**
Identical guidance to T2292 (1/3) and T2367 (3/3); track together using the T2292 checklist. Suggested evidence slice for this part: the database.
- Record Supabase's at-rest encryption evidence for the production project.
- Enable PITR on production; perform and document a restore drill into a scratch project.
- Retention schedule for observations, alarm events and reports approved and implemented (e.g. `pg_cron` job via migration).
- Database role access reviewed: only `authenticated` via RLS, `service_role` used only by the API, no extra login roles with broad grants.

**Status:** Documented
