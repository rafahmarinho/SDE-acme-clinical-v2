---
name: t2601-use-transparent-data-encryption-with-enterprise-da
description: Transparent Data Encryption (TDE) for Oracle/SQL Server/IBM is not applicable to ACME Clinical, which uses hosted Supabase PostgreSQL; at-rest protection is provided by Supabase's managed disk encryption and, for selected fields, pgcrypto.
---

# T2601: Use Transparent Data Encryption with Enterprise Databases (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2601](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2601/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** Enable the Transparent Data Encryption feature of enterprise databases (Oracle, Microsoft SQL Server, IBM) for whole tables, columns or cells so that data stays encrypted on storage media and is decrypted transparently for authorized access.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: the database is hosted Supabase PostgreSQL; no Oracle, SQL Server or IBM database is part of the stack.
- Missing: TDE is a vendor feature of enterprise database engines. Community PostgreSQL (and therefore Supabase) has no TDE switch, and nothing in `supabase/migrations/` or `backend/` can enable it.
- Conclusion: Not applicable as written. The nearest equivalent is platform-level at-rest encryption, which Supabase provides on its managed storage volumes (AES-256) and which is outside the repo. Field-level encryption with `pgcrypto`/Supabase Vault is covered by T2621 and T2665.

**Recommended Action:** Record T2601 as "not applicable – PostgreSQL on Supabase". Have the platform owner confirm in Supabase documentation/trust center (and the DPA for the chosen plan and region) that database volumes and backups are encrypted at rest, and keep that evidence with the project's security documentation. Track field-level encryption decisions under T2621.

**Status:** Documented
