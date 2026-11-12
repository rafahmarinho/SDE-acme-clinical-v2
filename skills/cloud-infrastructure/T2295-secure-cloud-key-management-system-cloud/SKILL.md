---
name: t2295-secure-cloud-key-management-system-cloud
description: Secure key management for ACME Clinical using provider-managed facilities (Supabase managed encryption keys, Supabase Vault, JWT signing keys and API keys; Vercel Sensitive environment variables), with restricted access, resilience and regular rotation.
---

# T2295: Secure cloud key management system (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2295](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2295/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Use the provider's key management service, restrict access to it, ensure it is resilient and highly available, ensure it is itself encrypted and secure, and rotate keys regularly.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 47 "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um" (EN: complete [code], database configuration, initial data, environment variable examples and a...) and line 5 "...Supabase para PostgreSQL, login por e-mail e" (EN: ...Supabase for PostgreSQL, email login and...))
- Found: Secrets are delivered as environment variables (Vercel); Supabase manages disk encryption keys, Auth JWT signing keys and API keys. No dedicated KMS (e.g. AWS KMS) is in this stack.
- Missing: Key storage, HA and rotation mechanics are provider features configured in consoles.
- Conclusion: Platform control. Use of Supabase Vault for application secrets can be expressed in `supabase/migrations/`; variable names (never values) are documented in `.env.example` files.

**Recommended Action:**
- Provider KMS equivalents:
  - Supabase: at-rest encryption keys are provider-managed (no customer action beyond evidence). Use Supabase Vault (`vault.create_secret`) for any secret that must live in the database (e.g. simulated integration credentials) instead of plain columns.
  - Supabase Auth: migrate to asymmetric JWT signing keys (JWT Signing Keys page) so keys can be rotated with a standby key; the API verifies tokens via the project JWKS endpoint, not a hard-coded shared secret.
  - Supabase API keys: use the new publishable/secret keys; create separate secret keys per consumer (API, CI) so one can be revoked independently.
  - Vercel: store secrets as Sensitive environment variables (write-only), scoped per environment; enable the team policy enforcing Sensitive env vars if available.
- Restrict access: only Owners may view/rotate Supabase keys and edit Vercel Production env vars (see T2287).
- Resilience: provider-managed and highly available; keep an offline, access-controlled record of how to regenerate each key (not the key itself) in the runbook.
- Rotation: rotate JWT signing keys and secret keys at least yearly and immediately on exposure; rotate DB password every 90 days; redeploy the API after env var rotation.
- If the organization requires customer-managed keys (BYOK) for PHI, this needs Supabase Enterprise discussions or an external KMS; record as a residual risk/decision.

**Status:** Documented
