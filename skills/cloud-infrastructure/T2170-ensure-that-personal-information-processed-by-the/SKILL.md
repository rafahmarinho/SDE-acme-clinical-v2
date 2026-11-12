---
name: t2170-ensure-that-personal-information-processed-by-the
description: Ensure ACME Clinical patient and staff data processed on Vercel and Supabase stays in jurisdictions that meet data localization requirements, by choosing compliant Supabase project and Vercel function regions, assessing cross-border transfers and keeping a transfer register.
---

# T2170: Ensure that personal information processed by the application meets data localization requirements (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2170](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T2170/)
**Priority:** 9/10 · **Phase:** requirements

**Guidance:** Identify the information assets and where they are processed, research localization rules for each jurisdiction, select compliant hosting providers and regions, self-assess before any cross-border transfer (halting it if needed), keep records of transfers (date, recipient, volume, sensitivity), and decide whether local replication satisfies the requirement or the only copy must stay in-country.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" and line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no")
- Found: hosted Supabase (PostgreSQL, Auth, Storage, Realtime) and two Vercel projects; the PRD names no country, region or regulation, and the demo uses fictitious patients.
- Missing: the target jurisdiction(s), applicable laws (e.g. LGPD, GDPR, HIPAA) and the provider region choices - all decided outside the code. Region is fixed when the Supabase project is created and set in Vercel project settings.
- Conclusion: Compliance/infrastructure decision. A repo-side part exists: the Vercel function region can be pinned in `backend/vercel.json` (`"regions": [...]`) to match the Supabase project region, and the chosen regions and transfer register belong in `docs/security/deployment.md` and `docs/security/privacy.md`.

**Recommended Action:** Privacy officer with platform owner: (1) determine the jurisdictions of patients and staff and their localization rules; (2) create the production Supabase project in a compliant region (e.g. `sa-east-1` São Paulo for Brazil, an EU region for GDPR) - region cannot be changed later; (3) pin Vercel function regions for the API to the same area (`backend/vercel.json` `regions`, Vercel project Functions settings) and check where Vercel logs and log drains store data; (4) review sub-processors (e-mail/SMTP provider, SIEM, backup storage) for data location; (5) keep a register of any cross-border transfer with date, recipient, volume and sensitivity; (6) decide whether backups/replicas outside the region are permitted.

**Status:** Applied
