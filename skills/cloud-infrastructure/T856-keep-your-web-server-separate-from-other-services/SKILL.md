---
name: t856-keep-your-web-server-separate-from-other-services
description: Keep ACME Clinical's web serving separate from other services; on Vercel and Supabase this means separate projects per function (static frontend, FastAPI API, managed database/auth/storage) and no mail, DNS or database roles bundled into the web tier.
---

# T856: Keep your web server separate from other services (NON-CODE)

**Category:** INFRA
**SD Elements:** [T856](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T856/)
**Priority:** 5/10 · **Phase:** deployment

**Guidance:** Run only the services a web server needs so its primary function is serving web content; do not combine it with mail, DNS, databases or middleware.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: The PRD already separates the frontend and API into separate Vercel deployments, and the database/auth/files/realtime into Supabase.
- Missing: There is no customer-managed web server host on which other daemons could be installed; Vercel controls the serving runtime.
- Conclusion: Largely satisfied by architecture and provider-managed. The design decision (keep services split) is expressed by the repo layout and the two `vercel.json` files.

**Recommended Action:**
- Keep the separation: frontend Vercel project serves only static assets (no serverless functions with secrets); the API project serves only the FastAPI app; database, Auth, Storage and Realtime remain in Supabase.
- Do not add unrelated services to the API project (e.g. an SMTP relay, cron-based data processing unrelated to the API, or a self-hosted database). Use Supabase Auth's SMTP configuration (custom SMTP provider) for password-recovery email, and Vercel Cron Jobs only for API-related tasks, documented in `backend/vercel.json`.
- DNS for custom domains handled by the registrar/DNS provider or Vercel DNS, not by application code.
- Review at each architecture change that new components are separate projects with their own least-privilege env vars.

**Status:** Documented
