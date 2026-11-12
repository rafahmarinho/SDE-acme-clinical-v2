---
name: t367-mitigate-the-security-risks-of-power-cut-and-power
description: Power-cut and power-supply-switch protections (UPS, shielded and redundant cabling, voltage monitors) for ACME Clinical are owned by Vercel/Supabase data centres and the hospital/organization facilities; the app-side duty is a defined degraded mode that never bypasses security.
---

# T367: Mitigate the security risks of power cut and power supply switch (NON-CODE)

**Category:** INFRA
**SD Elements:** [T367](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T367/)
**Priority:** 5/10 · **Phase:** architecture-design

**Guidance:** Identify features that must survive a power cut or switch to a secondary supply (UPS), especially security-related functions; define and review a degraded mode; design those features to be unaffected by the switch; physically protect and duplicate power cabling; use automatic voltage monitors.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 37 "Simule leituras normais, saturação baixa, bateria fraca, problema no sensor e" (EN: Simulate normal readings, low saturation, low battery, sensor problem and))
- Found: Servers run in Vercel and Supabase data centres. The "low battery" condition in the PRD is a simulated monitor scenario, not a real power system.
- Missing: No ACME-operated power infrastructure; physical power protection is the providers' and the facility's responsibility.
- Conclusion: Physical/facility control. Only the degraded-mode definition touches the application design.

**Recommended Action:**
- Providers: rely on Vercel's and Supabase's (and their IaaS's) data-centre power redundancy; file SOC 2 evidence of environmental controls.
- Organization/hospital facilities: workstations and network equipment at nursing stations used to view ACME Clinical should be on UPS-backed circuits; physical cabling protection and voltage monitoring are facilities' responsibility.
- Degraded mode (design note for the app team): when the client loses connectivity or a provider is unavailable, the frontend shows stale-data warnings, keeps the session locked to the same authorization rules, and never falls back to an unauthenticated or cached-privilege mode; on reconnect, tokens are revalidated with Supabase Auth.
- Simulated "low battery" scenario must keep alarms visible and acknowledgeable only by authorized roles (app behaviour, verified elsewhere).

**Status:** Documented
