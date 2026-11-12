---
name: t2289-secure-network-access-control-cloud-1-4
description: Apply least-privilege network access control to ACME Clinical's managed Vercel and Supabase environments (separate production from dev/preview, restrict direct database access, firewall rules, minimal public exposure). VPCs and NACLs are provider-managed. Part 1/4 of a shared countermeasure.
---

# T2289: Secure network access control (Cloud) (1/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2289](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2289/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Use the default VPC only for test/dev; configure routing tables and network ACLs with least privilege; apply per-server firewall rules allowing only required ports/services; use secure Internet gateways and assign public IPs only where required.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 5 "...Supabase para PostgreSQL..." (EN: ...Supabase for PostgreSQL...))
- Found: Vercel serverless functions and CDN; hosted Supabase. No VPC, subnet, NAT or security-group concepts are exposed by either platform on standard plans.
- Missing: VPC/routing/NACL objects do not exist in this stack; their nearest equivalents are Vercel Firewall, Deployment Protection, Vercel Secure Compute (Enterprise), Supabase Network Restrictions and Supabase PrivateLink (Enterprise).
- Conclusion: Network layer is managed by Vercel and Supabase; the customer-side equivalents are console settings. Some firewall rules and headers can also be expressed in `vercel.json`.

**Recommended Action:**
This is part 1/4. T2289, T2362, T2363 and T2364 have identical guidance; track together. This file is the master checklist.
- "Default VPC only for dev" equivalent: use separate Supabase projects for production and for dev/preview (or Supabase Branching), and separate Vercel environments (Production vs Preview) with distinct env vars. Never point Preview deployments at the production database.
- Routing/NACL equivalent (Supabase): enable Network Restrictions (Project Settings > Database > Network Restrictions) so direct Postgres and pooler connections are accepted only from approved CIDRs (admin office/VPN, CI runners). The FastAPI API on Vercel should use the Supabase HTTPS APIs, or, if it needs direct Postgres, use Vercel Secure Compute static egress IPs (Enterprise) added to the allowlist. Note that Network Restrictions do not cover the HTTPS Data API; that surface is protected by RLS and keys.
- Expose only the schemas needed via the Data API (Settings > API > Exposed schemas); keep internal schemas unexposed.
- Firewall rules equivalent (Vercel): enable Vercel Firewall managed rulesets (OWASP core where available, bot protection), add custom rules to block unused methods/paths, rate-limit `/auth`-adjacent and simulation endpoints (`/simulation/*`), and enable Attack Challenge Mode during incidents.
- Public exposure: enable Deployment Protection (Vercel Authentication or Password Protection) on Preview deployments and on any non-public environment; restrict the API's CORS allowlist in `backend/app/main.py` to the frontend's production domain.
- Repo config: security headers and route-level `mitigate` deny/challenge rules in `frontend/vercel.json` and `backend/vercel.json`; Supabase settings optionally via `supabase/config.toml` for local parity.

**Status:** Documented
