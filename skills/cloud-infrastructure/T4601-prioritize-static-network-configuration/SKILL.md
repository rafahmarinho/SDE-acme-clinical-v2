---
name: t4601-prioritize-static-network-configuration
description: Static IP/network configuration is not feasible on ACME Clinical's Vercel and Supabase platforms (dynamic, provider-managed addressing); use the hybrid approach of stable DNS names, Vercel Secure Compute static egress where needed, and Supabase network allowlists for admin networks.
---

# T4601: Prioritize static network configuration (NON-CODE)

**Category:** INFRA
**SD Elements:** [T4601](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T4601/)
**Priority:** 8/10 · **Phase:** deployment

**Guidance:** Configure hosts and devices with static IPs and network settings where feasible to improve stability and reduce DHCP/spoofing risks; where cloud or dynamic environments require DHCP, use a hybrid approach with compensating controls (DHCP snooping, IP-MAC binding).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 29 "...Use pacientes fictícios e monitores simulados..." (EN: ...Use fictional patients and simulated monitors...))
- Found: Serverless/managed hosting with provider-assigned, dynamic addressing; monitors are simulated in Python, so there are no physical hospital devices on a ward network.
- Missing: No customer-controlled hosts or LAN where static IPs could be set.
- Conclusion: The guidance's own "operational constraints" exception applies (cloud infrastructure). Static addressing is a provider and organization-network concern.

**Recommended Action:**
- Rely on stable DNS names (custom domains on Vercel with DNSSEC at the registrar where supported; Supabase project hostname) rather than IPs in configuration; never hard-code provider IPs.
- If the Supabase database must only accept the API, use Vercel Secure Compute (Enterprise) for static egress IPs and allowlist them in Supabase Network Restrictions; otherwise allowlist only admin office/VPN static IPs.
- Organization IT: administrators' office/VPN egress should use static IPs so the allowlist stays tight; apply DHCP snooping/IP-MAC binding on corporate networks used for administration.
- If real bedside monitors are integrated in future, the hospital network team should assign static addresses/reservations on an isolated medical device VLAN; record this as a future requirement.

**Status:** Documented
