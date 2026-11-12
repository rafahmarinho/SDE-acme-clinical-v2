---
name: t2621-use-file-volume-encryption-and-consider-in-databas
description: Rely on Supabase's managed volume encryption for ACME Clinical's PostgreSQL data and evaluate pgcrypto or Supabase Vault for field-level encryption of sensitive clinical fields with keys kept outside the database.
---

# T2621: Use file volume encryption and consider in-database encryption with pgcrypto (PostgreSQL) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2621](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2621/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** PostgreSQL has no built-in TDE (only EnterpriseDB's hosted version). Encrypt the data volume with OS features (FDE/BitLocker), and/or encrypt data with the `pgcrypto` extension, which requires secure key storage and management.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 33 "registrar observações" (EN: "record observations"))
- Found: hosted Supabase PostgreSQL; clinical observations and patient records are stored (fictional in the demo).
- Missing: OS/volume access; volume encryption is applied by Supabase.
- Conclusion: Volume encryption is platform-managed. The pgcrypto part can be expressed in the repo if adopted: a migration in `supabase/migrations/` with `create extension if not exists pgcrypto with schema extensions;` and `bytea` columns written via `pgp_sym_encrypt(value, key)`, where the key comes from Supabase Vault or a backend env var, never from migrations, `seed.sql` or the frontend. Note pgcrypto prevents searching/filtering on those columns, which affects the PRD's search and filter features.

**Recommended Action:** Platform/data owner: (1) document Supabase at-rest volume encryption as the baseline control; (2) classify fields and decide whether any (e.g. free-text observations, contact details) need pgcrypto/Vault; (3) if so, define key storage and rotation and confirm with `select * from pg_extension where extname = 'pgcrypto';`; (4) do not encrypt fields required for search/filter unless a blind-index approach is designed.

**Status:** Documented
