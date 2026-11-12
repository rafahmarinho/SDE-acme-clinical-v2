---
name: t374-offload-http-request-handling-to-dedicated-modules
description: Offload ACME Clinical HTTP request handling protections (request buffering, connection limits, DDoS mitigation, WAF and rate limiting) to the Vercel edge network and Firewall in front of the FastAPI functions and SPA, keeping in-app limits only as defence in depth.
---

# T374: Offload HTTP request handling to dedicated modules (NON-CODE)

**Category:** INFRA
**SD Elements:** [T374](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T374/)
**Priority:** 7/10 · **Phase:** requirements

**Guidance:** Offload parts of request handling to the OS or platform (e.g. only passing complete requests to the server) and configure server-specific modules (firewall, QoS, security modules) to restrict client behaviour and mitigate resource-exhaustion and DoS attacks.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no" (EN: "React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the"))
- Found: both the SPA and the FastAPI API are deployed on Vercel; there is no self-managed web server (no nginx/Apache) to configure. The API already enforces body size, header, URL length and per-instance rate limits in `backend/app/core/middleware.py`, which notes that Vercel Firewall rate limits are the primary control.
- Missing: control over the edge proxy, connection handling and network-level DDoS mitigation, which Vercel provides and configures in the dashboard.
- Conclusion: Platform configuration. Vercel's edge buffers complete requests before invoking functions and provides DDoS mitigation; WAF custom rules and rate limits are configured in Vercel Firewall (optionally as code via the Vercel API/Terraform), not in application code. Supabase API gateway limits apply to direct Supabase traffic.

**Recommended Action:** Platform owner: (1) enable Vercel Firewall for the API project with rate-limit rules on `/v1/auth/*`, `/v1/files/*` uploads and `/v1/reports/export.csv`, and a general per-IP limit; (2) enable Attack Challenge Mode playbook for incidents; (3) restrict methods/paths not used by the API via WAF custom rules; (4) set function `maxDuration` and memory in `backend/vercel.json` to bound resource use per request; (5) review Supabase API rate limits and Auth rate limits (`supabase/config.toml` `[auth.rate_limit]`); (6) record the configuration in `docs/security/deployment.md` and test with a controlled load test.

**Status:** Documented
