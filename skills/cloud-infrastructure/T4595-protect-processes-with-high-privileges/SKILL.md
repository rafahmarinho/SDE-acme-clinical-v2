---
name: t4595-protect-processes-with-high-privileges
description: Protect high-privilege processes behind ACME Clinical (Vercel function runtime, Supabase PostgreSQL, Auth and Storage services, and staff workstations) with platform isolation, integrity controls, anti-injection defences and monitoring, which are managed by Vercel, Supabase and organization IT rather than the application code.
---

# T4595: Protect processes with high privileges (NON-CODE)

**Category:** INFRA
**SD Elements:** [T4595](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T4595/)
**Priority:** 8/10 · **Phase:** requirements

**Guidance:** Identify high-privilege processes (OS, credential management, security software, kernel drivers, database and directory services, network configuration), protect them with trusted execution (PPL, SELinux/AppArmor, WDAC/IMA), block process injection (CFG, EDR/HIPS), minimise their privileges and isolate them (sandboxes, namespaces, ACLs), and monitor process creation and modification through a SIEM.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no" and line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e")
- Found: the API runs as Vercel serverless functions and the database, Auth and Storage are hosted Supabase services; the project has no servers, kernels or OS processes of its own.
- Missing: access to the host OS, kernel and process controls of the Vercel and Supabase infrastructure; these are operated by the providers. Staff workstations are managed by organization IT.
- Conclusion: Platform/infrastructure responsibility (shared-responsibility model). The in-repo equivalent is least privilege for the application's own "privileged processes": the API connects as dedicated non-superuser roles (`acme_api`, `acme_api_rw`, `acme_reset_owner` in `supabase/migrations/0002_roles_rls.sql`, `0003_authz_rbac.sql`), `security definer` functions pin `search_path`, and the service role key is confined to the backend - already covered by authorization/database skills.

**Recommended Action:** Platform owner / IT: (1) obtain and file Vercel and Supabase SOC 2 / ISO 27001 reports covering host hardening, process isolation and monitoring; (2) limit who can act with platform-level privilege (Vercel team owners, Supabase org owners) and require SSO + MFA (see T2285/T2286); (3) never run the backend with the Supabase `postgres` superuser or expose the service role key outside Vercel server env vars; (4) on clinical workstations, enable OS protections (Windows LSASS PPL, WDAC, Exploit Protection/CFG; SELinux/AppArmor on Linux), deploy EDR, and forward process telemetry to the SIEM; (5) review these controls annually.

**Status:** Documented
