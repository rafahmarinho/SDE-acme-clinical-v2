---
name: t2603-protect-backup-archive-bits
description: Protecting file-system archive bits is not applicable to ACME Clinical because data is stored in Supabase PostgreSQL and Storage with snapshot/WAL-based backups; the equivalent is keeping Supabase backup and PITR coverage complete.
---

# T2603: Protect backup archive bits (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2603](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2603/)
**Priority:** 7/10 · **Phase:** deployment

**Guidance:** Full and incremental file backups clear the archive bit and file edits set it again; ensure nothing else in the system or application changes archive bits, or incremental backups may miss changed files.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: data lives in hosted Supabase; Vercel serverless functions have no persistent disk.
- Missing: a file server or file-based incremental backup tool that uses archive bits.
- Conclusion: Not applicable. Supabase database backups use physical snapshots and WAL (PITR); there is no archive-bit mechanism to protect.

**Recommended Action:** Mark T2603 "not applicable – no archive-bit based backups". Map the intent to Supabase: ensure daily backups/PITR are enabled for production and that any separate Storage backup job copies all objects modified since the last run (e.g. based on object `updated_at`), owned by ops.

**Status:** Documented
