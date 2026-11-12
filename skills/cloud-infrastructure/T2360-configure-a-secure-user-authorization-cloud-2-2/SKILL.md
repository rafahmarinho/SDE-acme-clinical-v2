---
name: t2360-configure-a-secure-user-authorization-cloud-2-2
description: Apply least-privilege, group-based authorization to ACME Clinical's Vercel and Supabase console users. Part 2/2 of a shared countermeasure tracked with T2287.
---

# T2360: Configure a secure user authorization (Cloud) (2/2) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2360](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2360/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Restrict IAM administration to a small group of trusted users, apply least privilege to every policy, and attach policies to groups/roles rather than individual users (justify any user-specific policy).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: Vercel and Supabase host the system; console roles are not described.
- Missing: Role assignment happens in Vercel/Supabase/IdP.
- Conclusion: Platform/IT control.

**Recommended Action:**
Identical guidance to T2287 (1/2); track together using the T2287 checklist. Suggested evidence slice for this part: group mapping and exceptions.
- IdP groups (e.g. `acme-clinical-admins`, `acme-clinical-devs`, `acme-clinical-viewers`) mapped to Vercel and Supabase roles via SSO/directory sync where the plan allows.
- A register of any user-specific grants (e.g. an external contractor with project-only access) with justification, owner and expiry date.
- Quarterly access review sign-off.

**Status:** Documented
