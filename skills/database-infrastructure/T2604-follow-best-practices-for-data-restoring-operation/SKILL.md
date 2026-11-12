---
name: t2604-follow-best-practices-for-data-restoring-operation
description: Define and rehearse a documented restore procedure for ACME Clinical's Supabase PostgreSQL (daily backups/PITR) with recovery-time targets, a restoration checklist and integrity checks; the in-app demo data reset is not a restore mechanism.
---

# T2604: Follow best practices for data restoring operations (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2604](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2604/)
**Priority:** 7/10 · **Phase:** deployment

**Guidance:** SLAs and disaster recovery plans should state how long each database restore takes and how corruption is ruled out. Test recovery regularly, keep a restoration checklist, verify backup size/integrity with alerting, do not rush restores, keep the plan simple and share it with responsible personnel.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 43 "avançar a simulação, consultar eventos e reiniciar os dados" (EN: "advance the simulation, view events and reset the data"))
- Found: hosted Supabase PostgreSQL. "Reiniciar os dados" is a simulation feature that reloads demo data; it is not a backup/restore mechanism and must not be treated as one.
- Missing: restore operations are performed through Supabase (daily backups, PITR add-on, restore to new project) and organizational DR processes.
- Conclusion: Operational/platform process. The repo can hold the runbook (e.g. a restore section in the README requested by the PRD) and a post-restore verification SQL (row counts per table, RLS enabled, migration version matches `supabase/migrations/`).

**Recommended Action:** Platform/ops owner: (1) define RTO/RPO for the database; (2) write a restore checklist: choose backup/PITR timestamp, restore to a new Supabase project first, re-apply secrets/env vars in Vercel, run integrity checks, then switch over; (3) rehearse a restore at least quarterly and record duration; (4) alert on failed backups (Supabase dashboard/billing notifications or external monitoring); (5) share the runbook with the on-call team.

**Status:** Documented
