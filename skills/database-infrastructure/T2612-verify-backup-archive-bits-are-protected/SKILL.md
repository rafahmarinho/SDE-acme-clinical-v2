---
name: t2612-verify-backup-archive-bits-are-protected
description: Verification of file-system archive bits is not applicable to ACME Clinical, whose data lives in Supabase PostgreSQL and Storage; the equivalent check is that Supabase backup/PITR coverage is complete and not disrupted.
---

# T2612: Verify backup archive bits are protected (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2612](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2612/)
**Priority:** 7/10 · **Phase:** testing

**Guidance:** Verify that file archive bits change only when files are opened and modified, and that no other system or application activity alters them.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: all persistent data is in hosted Supabase (PostgreSQL, Storage); the apps run serverless on Vercel with no persistent file system.
- Missing: any file-based backup that relies on archive bits (a Windows/NTFS-style incremental backup concept).
- Conclusion: Not applicable. Supabase backups are snapshot/WAL-based (PITR), so incremental coverage depends on continuous WAL archiving, not archive bits.

**Recommended Action:** Mark T2612 "not applicable – no file-system backups". Equivalent check by ops: confirm PITR/daily backup coverage has no gaps (backup list in Supabase Dashboard shows expected daily entries; PITR window is continuous) and that Storage bucket backups, if implemented, capture all modified objects.

**Status:** Documented
