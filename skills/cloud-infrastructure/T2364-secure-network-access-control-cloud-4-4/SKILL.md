---
name: t2364-secure-network-access-control-cloud-4-4
description: Apply least-privilege network access control to the path between ACME Clinical's Vercel-hosted API and Supabase (egress, CORS, environment separation). Part 4/4 of a shared countermeasure tracked with T2289.
---

# T2364: Secure network access control (Cloud) (4/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2364](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2364/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Use the default VPC only for test/dev; least-privilege routing tables and NACLs; per-server firewall rules for required ports only; secure Internet gateways and minimal public IPs.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: The API runs as Vercel functions and talks to hosted Supabase. Default Vercel function egress uses dynamic shared IPs.
- Missing: Static egress / private connectivity requires Vercel Secure Compute (Enterprise) and/or Supabase PrivateLink, configured outside the repo.
- Conclusion: Platform control; CORS and environment wiring are partly repo config.

**Recommended Action:**
Identical guidance to T2289 (1/4), T2362 (2/4) and T2363 (3/4); track together using the T2289 checklist. Suggested evidence slice for this part: the API-to-database path.
- Decide and document whether the API uses the Supabase HTTPS APIs (no IP allowlist possible; rely on keys + RLS) or direct Postgres (allowlist Secure Compute egress IPs in Supabase Network Restrictions).
- The Supabase service-role/secret key is set only on the API project's Production environment as a Sensitive env var; never on the frontend project.
- CORS allowlist in `backend/app/main.py` limited to the frontend production domain (and explicit preview domains if needed), configured via env var documented in `backend/.env.example`.
- Preview API deployments point to a non-production Supabase project.

**Status:** Documented
