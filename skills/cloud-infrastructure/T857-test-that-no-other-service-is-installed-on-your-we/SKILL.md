---
name: t857-test-that-no-other-service-is-installed-on-your-we
description: Test that ACME Clinical's Vercel web/API deployments expose only the intended web service; host-level service listing (chkconfig) is not possible on serverless, so the test uses external port scans and deployment configuration review.
---

# T857: Test that no other service is installed on your web server (NON-CODE)

**Category:** INFRA
**SD Elements:** [T857](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T857/)
**Priority:** 5/10 · **Phase:** testing

**Guidance:** List enabled services with the OS service manager (e.g. `chkconfig --list | grep ':on'` on Red Hat) and compare them with documented business needs; fail if extra services run.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Serverless Vercel deployments; no shell access to the underlying host.
- Missing: OS service managers are not accessible; host services are Vercel-managed.
- Conclusion: Adapt the test to black-box checks and configuration review.

**Recommended Action:**
Test procedure:
- `nmap -Pn -p- <frontend-domain>` and `<api-domain>`: only 80 (HTTP->HTTPS redirect) and 443 should answer. Fail on anything else and escalate to Vercel.
- Review the Vercel deployment's function list (Deployment > Functions/Resources): frontend project has no unexpected functions; API project exposes only the FastAPI entrypoint and any documented Cron Jobs.
- Review installed Vercel Integrations (Team Settings > Integrations) and remove any not justified.
- Request each undocumented route the API might expose by default (e.g. `/docs`, `/redoc`, `/openapi.json`) in production; fail if FastAPI interactive docs are enabled in production without justification (app-side setting in `backend/app/main.py`).
- Record results against the documented list of required services.

**Status:** Documented
