---
name: t2307-verify-that-the-key-management-system-is-secured-c
description: Verify that ACME Clinical's provider-managed key facilities (Supabase keys, JWT signing keys, Vault; Vercel Sensitive environment variables) are access-restricted, resilient, encrypted and rotated on schedule.
---

# T2307: Verify that the key management system is secured (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2307](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2307/)
**Priority:** 10/10 · **Phase:** testing

**Guidance:** Verify use of provider key management, restricted access, durability/high availability, encryption and security of the KMS itself, and key rotation at appropriate intervals.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 47 "...exemplos de variáveis de ambiente..." (EN: ...environment variable examples...))
- Found: Secrets via Vercel env vars; keys managed by Supabase.
- Missing: Verification targets provider settings configured per T2295.
- Conclusion: Manual/operational verification.

**Recommended Action:**
Checklist:
- [ ] All API secrets on Vercel are marked Sensitive and scoped per environment; none present on the frontend project except the publishable/anon key and URLs.
- [ ] Supabase JWT signing keys: asymmetric key in use with a documented rotation date; API validates via JWKS.
- [ ] Separate Supabase secret keys per consumer; last rotation within policy; revoked keys no longer authenticate (test with `curl`).
- [ ] Only Owners can view keys (test with a Developer/Read-only account).
- [ ] Database secrets stored with Supabase Vault, not plain columns (query `information_schema.columns` for suspicious names like `%secret%`, `%token%`).
- [ ] Provider attestation (SOC 2) covers key management durability and encryption.

**Status:** Documented
