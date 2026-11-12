---
name: t2365-secure-data-in-transit-cloud-2-2
description: Enforce TLS and secure key/certificate handling for ACME Clinical traffic on Vercel and Supabase. Part 2/2 of a shared countermeasure tracked with T2290.
---

# T2365: Secure data in transit (Cloud) (2/2) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2365](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2365/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Enforce encrypted protocols such as TLS, use secure protocol versions, store secret keys and certificates securely, and rotate them regularly without letting certificates expire.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 47 "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um" (EN: complete [code], database configuration, initial data, environment variable examples and a...))
- Found: Vercel and Supabase terminate TLS; secrets are supplied as environment variables.
- Missing: TLS configuration and certificate lifecycle are platform-managed.
- Conclusion: Platform control; header and URL configuration is repo config.

**Recommended Action:**
Identical guidance to T2290 (1/2); track together using the T2290 checklist. Suggested evidence slice for this part: key and certificate lifecycle.
- Inventory of secrets (Supabase secret/service-role key, DB password, JWT signing key, Vercel tokens, custom-domain certificates) with owner, storage location, last rotation and next rotation date.
- `.env.example` files contain placeholder names only, no real values; a secret scanner (e.g. gitleaks) runs in CI.
- Rotation runbook tested once in a non-production project.

**Status:** Documented
