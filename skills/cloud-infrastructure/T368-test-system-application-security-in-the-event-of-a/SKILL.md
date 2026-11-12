---
name: t368-test-system-application-security-in-the-event-of-a
description: Test ACME Clinical's behaviour when power or connectivity is lost and restored (client workstation power-off, network drop, provider outage simulation) to confirm security controls are not bypassed in degraded mode; physical power protection checks belong to facilities and providers.
---

# T368: Test system/application security in the event of a power cut or power supply switch (NON-CODE)

**Category:** INFRA
**SD Elements:** [T368](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T368/)
**Priority:** 5/10 · **Phase:** testing

**Guidance:** Identify functions required during a power cut/switch, simulate the event and fail if they become unavailable or security is compromised; test that degraded mode does not bypass security; verify power sources and cables are physically protected.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 45 "devem aparecer nas telas e continuar salvos após recarregar a aplicação." (EN: must appear on screen and remain saved after reloading the application.))
- Found: Servers are in Vercel/Supabase data centres; the team cannot cut their power.
- Missing: Physical power infrastructure under ACME control.
- Conclusion: Server-side power testing is a provider responsibility; the team can test client-side power/connectivity loss and the degraded-mode security properties.

**Recommended Action:**
Test procedure (QA/security, staging with demo data):
- Client power cut: while logged in as a nurse on the live monitoring screen, hard power-off (or kill) the browser/workstation; on restart confirm the session either requires re-authentication or resumes only with a still-valid Supabase session, with the same role restrictions. Fail if a privileged view (administrator or simulation reset) is accessible without valid auth.
- Network drop mid-action: disconnect during an alarm acknowledgement and an observation save; on reconnect confirm the action is either committed once (idempotent) or clearly failed, and data persists after reload as the PRD requires.
- Provider outage simulation: block `*.supabase.co` in the browser/DNS; confirm the UI shows an error/stale-data state and does not expose cached data from another user.
- Physical power protection: obtain facilities' confirmation that nursing-station workstations/network gear are UPS-backed; obtain provider SOC 2 environmental-control evidence. Fail if not documented.

**Status:** Documented
