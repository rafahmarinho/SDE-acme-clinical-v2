---
name: t2665-protect-sensitive-data-at-rest-with-encryption
description: Ensure patient and vital-sign data stored in ACME Clinical's Supabase PostgreSQL and Storage are encrypted at rest through Supabase's managed volume encryption, with optional field-level encryption for the most sensitive columns.
---

# T2665: Protect sensitive data at rest with encryption (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2665](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2665/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** Use file-system/full-disk encryption on database servers; enable integrated at-rest encryption (TDE) where the database offers it; otherwise decide per policy whether disk encryption suffices or whether application-side field encryption, trusted extensions or platform services are needed, keeping key management risks in mind.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 29 "Use pacientes fictícios e monitores simulados" (EN: "Use fictional patients and simulated monitors"))
- Found: hosted Supabase PostgreSQL and Storage; patient data is fictional for the demo but models clinical records (observations, readings).
- Missing: control of disk/volume encryption, which Supabase applies to managed database volumes, backups and Storage.
- Conclusion: Platform responsibility. Optional repo contribution: a migration in `supabase/migrations/` enabling `pgcrypto` or Supabase Vault for specific high-sensitivity fields (e.g. free-text observations) with keys held outside the database (Vercel env var / Vault secret), never in migrations or `seed.sql`. See T2621.

**Recommended Action:** Platform/compliance owner: (1) confirm and document Supabase's at-rest encryption (AES-256) for the database, backups and Storage buckets for the chosen region/plan; (2) decide per data classification whether field-level encryption is required before real patient data is ever stored; (3) if required, adopt pgcrypto/Vault with a documented key-rotation procedure; (4) keep Storage buckets private and serve files via signed URLs.

**Status:** Documented
