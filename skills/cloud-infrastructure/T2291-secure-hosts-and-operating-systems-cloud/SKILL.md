---
name: t2291-secure-hosts-and-operating-systems-cloud
description: Host and OS hardening for ACME Clinical is delegated to Vercel (serverless function runtime) and Supabase (managed Postgres hosts); the customer-side equivalents are pinned runtimes, minimal dependencies, approved build images and least-privilege function credentials.
---

# T2291: Secure hosts and operating systems (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2291](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2291/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Restrict access to OS images, use minimal images, use built-in OS security features, use the provider's automated patching, create instances only from approved images, and restrict permissions assigned to each instance.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 17 "O sistema médico vai se chamar ACME Clinical. Use Python com FastAPI e Pydantic no backend e" (EN: The medical system will be called ACME Clinical. Use Python with FastAPI and Pydantic on the backend and...) and line 19 "...publicados separadamente na Vercel." (EN: ...published separately on Vercel.))
- Found: The FastAPI backend runs as Vercel Python functions; the frontend is static assets on Vercel's CDN; PostgreSQL runs on Supabase-managed hosts.
- Missing: There are no customer-managed instances, OS images or patch schedules; Vercel and Supabase own host hardening and patching.
- Conclusion: Provider responsibility under the shared-responsibility model. Customer equivalents are partly repo config: Python version pin, `backend/requirements.txt`/lockfile, `backend/vercel.json` function settings, `frontend` `packageManager` pin.

**Recommended Action:**
- Provider assurance: file Vercel's and Supabase's SOC 2 Type II reports (and HIPAA BAA if real PHI is ever processed) as evidence that host OS hardening and patching are managed.
- "Approved/minimal images" equivalent:
  - Pin a supported Python runtime for the API (e.g. `.python-version` / `requires-python` honoured by Vercel) and a supported Node.js version for the frontend build (Project Settings > Node.js Version, plus `engines` / `packageManager` in `frontend/package.json`).
  - Keep dependencies minimal and locked (`backend/requirements.txt` with pinned versions/hashes, `pnpm-lock.yaml`); enable Dependabot/Renovate so runtime patches are applied promptly.
- Supabase: apply Postgres version upgrades offered in the dashboard (Infrastructure settings) within a defined window; review Security Advisor.
- Instance permissions equivalent: the API function only receives the env vars it needs (scoped per environment); the frontend project has no server secrets; no long-lived broad tokens in function env.
- Restrict access to "images": only Vercel Owners can change build/runtime settings; Git branch protection prevents unreviewed changes to build config.

**Status:** Documented
