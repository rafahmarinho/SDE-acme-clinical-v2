---
name: t2159-ensure-security-of-virtualized-environments-cloud
description: Virtualization and tenant isolation for ACME Clinical are provided by Vercel and Supabase; the customer-side duties are configuring the provided security features securely and identifying isolation gaps, as no containers or VMs are operated by the team.
---

# T2159: Ensure security of virtualized environments (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2159](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/activities/32-T2159/)
**Priority:** 10/10 · **Phase:** activities

**Guidance:** Providers must secure physical/virtualization infrastructure and tenant isolation with secure defaults; customers must configure virtualization services per best practice and identify gaps; container users must isolate containers, use approved images, apply RBAC to registries and secure orchestration.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Vercel functions (provider-isolated microVMs/containers) and Supabase-managed Postgres. The PRD and architecture include no Docker images, registries or orchestration.
- Missing: Customer-operated virtualization or container platform.
- Conclusion: Provider-side for isolation; customer-side "configure services securely" is spread across the other cloud CMs (network, data, IAM). The container section is not applicable unless a containerized component is added.

**Recommended Action:**
- As cloud customer:
  - Review Vercel and Supabase shared-responsibility docs and SOC 2 reports for tenant isolation; record gaps (e.g. shared egress IPs, shared Postgres hosts on smaller compute tiers).
  - Configure provided features per T2289 (Network Restrictions, Firewall), T2292 (private buckets, PITR), T2287 (roles) and T2290 (SSL enforcement).
  - For stronger isolation if required: dedicated Supabase compute add-on, separate Supabase projects per environment, Vercel Secure Compute.
- Containers: not used. If a local Docker setup is added for development (`supabase start` uses Docker locally), use only official Supabase CLI images and never expose local stack ports beyond localhost.

**Status:** Documented
