---
name: t2359-configure-a-secure-user-authentication-cloud-2-2
description: Secure authentication for ACME Clinical's Vercel and Supabase console users and automation tokens (MFA, least-privileged daily accounts, token rotation and removal). Part 2/2 of a shared countermeasure tracked with T2286.
---

# T2359: Configure a secure user authentication (Cloud) (2/2) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2359](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2359/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Enforce MFA for privileged users; do not use privileged accounts/keys for daily work; enforce strong passwords with expiry and no reuse; rotate credentials regularly and immediately on exposure; remove unused credentials; one active key per user; prefer temporary keys.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: Deployment and administration happen through Vercel and Supabase accounts.
- Missing: Console authentication and token lifecycle are account/team settings.
- Conclusion: Platform/IT control.

**Recommended Action:**
Identical guidance to T2286 (1/2); track together using the T2286 checklist. Suggested evidence slice for this part: credentials inventory and rotation.
- Export Vercel team tokens and Supabase access tokens; remove any unused or owner-less token; ensure one active token per person/CI job.
- Document rotation dates for Supabase secret/service-role key, DB password and Vercel tokens; rotate immediately if any appear in Git history, logs or chat.
- CI uses short-lived credentials (OIDC) where available; long-lived tokens stored only in the CI secret store.

**Status:** Documented
