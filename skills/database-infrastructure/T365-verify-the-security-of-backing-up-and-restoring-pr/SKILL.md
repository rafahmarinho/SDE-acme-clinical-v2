---
name: t365-verify-the-security-of-backing-up-and-restoring-pr
description: Verify that ACME Clinical's Supabase backup and restore procedures restore all data types correctly, survive interruption, protect backups like production data, and transfer data only over authenticated TLS channels.
---

# T365: Verify the security of backing up and restoring procedures (NON-CODE)

**Category:** INFRA
**SD Elements:** [T365](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T365/)
**Priority:** 6/10 · **Phase:** testing

**Guidance:** Back up different data types and restore them, failing the test if the system or data is not restored; interrupt a backup and confirm it resumes or restarts; verify backups receive the same protection as original data; verify transfers use TLS and the backup/restore server is authenticated.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 43 "reiniciar os dados" (EN: "reset the data"))
- Found: hosted Supabase PostgreSQL, Auth and Storage. "Reiniciar os dados" reloads demo data for the simulation; it is not a backup/restore and does not satisfy this test.
- Missing: backups are produced and stored by Supabase; restore is a Dashboard/support operation, not exercisable by app tests.
- Conclusion: Manual operational verification. Repo artifacts can support it: migrations in `supabase/migrations/` to rebuild schema and a documented post-restore check list (table row counts, Auth users present, Storage objects reachable, RLS enabled).

**Recommended Action:** QA/ops owner, per release or quarterly: (1) restore the latest backup or a PITR point into a new Supabase project and verify the app works against it (database rows, Auth users, Storage files restored separately); (2) for any self-run `pg_dump`, kill the job mid-run and confirm the next scheduled run completes; (3) confirm backup copies are encrypted and access-limited like production; (4) confirm dump/restore connections use `sslmode=verify-full`; (5) record results and failures.

**Status:** Documented
