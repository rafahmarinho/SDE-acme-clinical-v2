---
name: t2610-verify-that-transparent-data-encryption-is-utilize
description: Verification of Transparent Data Encryption for enterprise databases is not applicable to ACME Clinical's Supabase PostgreSQL; instead verify Supabase's managed at-rest encryption and any pgcrypto-encrypted columns.
---

# T2610: Verify that Transparent Data Encryption is utilized with Enterprise Databases (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2610](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2610/)
**Priority:** 8/10 · **Phase:** testing

**Guidance:** Verify that TDE is enabled for entire tables, columns or individual cells where appropriate, using the mechanism of the specific enterprise database product.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"))
- Found: hosted Supabase PostgreSQL is the only database; no Oracle, SQL Server or IBM engine.
- Missing: a TDE-capable engine. PostgreSQL has no TDE to verify, and storage encryption on Supabase is not observable from SQL or application code.
- Conclusion: Not applicable as written. The equivalent verification is a platform evidence check (Supabase at-rest encryption) plus, if field-level encryption is adopted (T2621), a SQL check that sensitive columns hold ciphertext (`bytea` from `pgp_sym_encrypt`) rather than plaintext.

**Recommended Action:** Testing/security owner: (1) collect Supabase's at-rest encryption statement for the project's plan/region as evidence; (2) if pgcrypto or Supabase Vault is used, run a manual check in the Supabase SQL editor that selected columns are not readable without the key; (3) mark T2610 "not applicable – no enterprise TDE engine" in SD Elements with that evidence attached.

**Status:** Documented
