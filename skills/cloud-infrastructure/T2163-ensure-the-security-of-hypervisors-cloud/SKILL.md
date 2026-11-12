---
name: t2163-ensure-the-security-of-hypervisors-cloud
description: Hypervisor security for ACME Clinical is entirely the responsibility of Vercel and Supabase (and their underlying IaaS); the customer action is vendor assurance and choosing isolation tiers where required.
---

# T2163: Ensure the security of hypervisors (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2163](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/activities/32-T2163/)
**Priority:** 9/10 · **Phase:** activities

**Guidance:** Harden hypervisors through monitoring of guest-to-host privileged operations, access control on hypervisor consoles and device access, separate management networks, trust-level separation, I/O limits, gold-standard signed VM images with patching, and memory/resource-exhaustion protections (per NIST SP 800-125A).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 5 "...Supabase para PostgreSQL..." (EN: ...Supabase for PostgreSQL...))
- Found: PaaS/serverless (Vercel) and DBaaS (Supabase, which itself runs on AWS). ACME Clinical has no hypervisor, VM image library or host hardware.
- Missing: Any customer access to the virtualization layer.
- Conclusion: Not applicable to the ACME Clinical team as an implementation task; it is a provider (and sub-provider) responsibility. Nothing can be expressed as repo config.

**Recommended Action:**
- Vendor risk management (security/compliance team): obtain and review Vercel's and Supabase's SOC 2 Type II reports and sub-processor lists (including the IaaS they run on) for virtualization/tenant-isolation controls; record review date.
- If real patient data is processed in future, require a HIPAA BAA and evaluate isolation tiers: Supabase dedicated compute sizes / Enterprise options and Vercel Secure Compute (dedicated network) to reduce noisy-neighbour and shared-infrastructure risk.
- Track provider security advisories (Vercel and Supabase status/security pages) and include hypervisor-escape class incidents in the incident response plan.

**Status:** Documented
