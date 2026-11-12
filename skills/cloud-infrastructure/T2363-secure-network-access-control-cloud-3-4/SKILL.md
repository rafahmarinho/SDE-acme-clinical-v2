---
name: t2363-secure-network-access-control-cloud-3-4
description: Apply least-privilege network access control at ACME Clinical's Vercel edge (Firewall rules, rate limits, Deployment Protection for previews). Part 3/4 of a shared countermeasure tracked with T2289.
---

# T2363: Secure network access control (Cloud) (3/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2363](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2363/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Use the default VPC only for test/dev; least-privilege routing tables and NACLs; per-server firewall rules for required ports only; secure Internet gateways and minimal public IPs.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Two Vercel projects. Vercel only serves HTTPS on 443 (HTTP 80 redirects); no ports or security groups are customer-configurable.
- Missing: Edge filtering is a Vercel Firewall/project setting.
- Conclusion: Platform control in Vercel; route-level rules may also live in `vercel.json`.

**Recommended Action:**
Identical guidance to T2289 (1/4), T2362 (2/4) and T2364 (4/4); track together using the T2289 checklist. Suggested evidence slice for this part: Vercel Firewall.
- Vercel Firewall custom rules: deny methods not used by the API (e.g. TRACE), deny paths not served (e.g. `/.env`, `/wp-*`), rate-limit API write endpoints and simulation controls.
- Managed rulesets (bot protection / AI bots) enabled per project where the plan allows.
- Attack Challenge Mode documented in the incident runbook.
- Deployment Protection enabled for Preview (Vercel Authentication); Trusted IPs (Enterprise) considered for the API's non-production environments.
- Repo config: route-level `mitigate` rules and security headers committed in `frontend/vercel.json` / `backend/vercel.json` where supported.

**Status:** Documented
