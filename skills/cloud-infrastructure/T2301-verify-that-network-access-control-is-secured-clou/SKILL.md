---
name: t2301-verify-that-network-access-control-is-secured-clou
description: Verify that ACME Clinical's Vercel and Supabase network controls (environment separation, database network restrictions, edge firewall rules, minimal public exposure) are in place and effective.
---

# T2301: Verify that network access control is secured (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2301](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2301/)
**Priority:** 10/10 · **Phase:** testing

**Guidance:** Verify the default VPC is not used in production, least privilege is applied to routing/NACLs, per-instance firewall rules limit traffic to required ports/services, and gateways and public IPs are minimal and secure.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel and hosted Supabase; no customer VPC.
- Missing: Verification targets are platform settings set by T2289/T2362/T2363/T2364.
- Conclusion: Manual/operational verification with some scriptable probes.

**Recommended Action:**
Checklist (ops/security):
- [ ] Production and non-production use different Supabase projects; Vercel Preview env vars do not contain production Supabase URL/keys.
- [ ] From a non-allowlisted IP, `psql "postgresql://...supabase.co:5432/postgres?sslmode=require"` is refused; from an allowlisted IP it succeeds.
- [ ] `psql ... sslmode=disable` is refused (SSL enforcement).
- [ ] Vercel Firewall custom rules and managed rulesets are listed and a request to a denied path/method returns 403.
- [ ] Rate-limit rule triggers (429) on repeated requests to a protected API path in a preview environment.
- [ ] Preview deployment URLs require Vercel Authentication.
- [ ] `nmap` against the frontend and API hostnames shows only 80 (redirect) and 443.
- [ ] CORS: `curl -H "Origin: https://evil.example" -I <api>/...` does not return `Access-Control-Allow-Origin` for that origin.

**Status:** Documented
