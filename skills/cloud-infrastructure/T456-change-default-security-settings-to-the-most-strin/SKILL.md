---
name: t456-change-default-security-settings-to-the-most-strin
description: Move ACME Clinical's Vercel and Supabase settings from defaults to the most stringent options, maintain an inventory of enabled features/endpoints, and disable unused ones (Auth providers, exposed schemas, preview access, integrations). USB/hardware portions are not applicable.
---

# T456: Change default security settings to the most stringent ones and disable unnecessary services and modules (NON-CODE)

**Category:** INFRA
**SD Elements:** [T456](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T456/)
**Priority:** 6/10 · **Phase:** deployment

**Guidance:** Replace default security settings with the most stringent available, maintain and periodically review an inventory of components, functions, services, protocols and ports (supplemented by scanning), disable everything not needed, keep one function per component, and secure USB ports (charging-only by default, password-protected mounting).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: Use current, stable technology versions and Supabase for PostgreSQL, email login and...) and line 9 "persistidos, com integrações externas simuladas." (EN: persisted, with simulated external integrations.))
- Found: Only email/password login, Storage, Realtime and PostgreSQL are required from Supabase; external integrations are simulated; monitors are simulated (no physical devices, so the USB section does not apply).
- Missing: Most defaults are provider console settings. Some can be committed as config.
- Conclusion: Platform control, partly expressible in `supabase/config.toml`, `supabase/migrations/` and `vercel.json`.

**Recommended Action:**
- Supabase (most stringent settings):
  - Auth: enable only the Email provider; disable anonymous sign-ins and unused OAuth providers; consider disabling public sign-ups (staff accounts created by administrators); require email confirmation; set minimum password length/complexity and leaked password protection; enable CAPTCHA on sign-in/sign-up/recovery; tighten rate limits; restrict Redirect URLs to the production frontend domain.
  - API: expose only needed schemas; disable GraphQL (`pg_graphql`) if unused; enable RLS on every table (Security Advisor clean).
  - Database: SSL enforcement on, Network Restrictions on, unused extensions dropped.
  - Storage: buckets private, file size and MIME limits set.
  - Realtime: only required tables in the `supabase_realtime` publication; use private channels with authorization.
- Vercel:
  - Deployment Protection on Preview (Vercel Authentication); disable public access to build logs/source (Project Settings > Security: "Build Logs and Source Protection").
  - Enable Firewall managed rules; remove unused Integrations; disable automatic deployments from forks/untrusted branches ("Git Fork Protection").
  - Security headers in `vercel.json` (HSTS, `X-Content-Type-Options`, `Referrer-Policy`, CSP, `Permissions-Policy`).
- Inventory: maintain a short table (in the README or ops docs) of enabled Supabase features, Vercel projects/functions, domains, ports (443) and integrations; review quarterly and after scans (`nmap`, `testssl.sh`, Supabase Advisors).
- USB/hardware ports: not applicable (simulated monitors; no ACME-operated devices).

**Status:** Documented
