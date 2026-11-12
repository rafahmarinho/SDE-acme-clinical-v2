---
name: t4597-break-and-inspect-ssl-tls-sessions
description: SSL/TLS break-and-inspect for ACME Clinical is an organization network/security-testing activity, not app code; limit it to authorized, isolated test environments with demo data, and never deploy interception in front of Vercel or Supabase production traffic.
---

# T4597: Break and inspect SSL/TLS sessions (NON-CODE)

**Category:** INFRA
**SD Elements:** [T4597](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T4597/)
**Priority:** 6/10 · **Phase:** development

**Guidance:** Inspect decrypted TLS traffic for adversary activity using a proxy (Burp, Fiddler, mitmproxy) with an organization root CA, after confirming legal authorization (GDPR/HIPAA), in an isolated environment; secure the root CA key (HSM/encrypted storage), log securely, filter scope, and revert all trust/configuration changes afterwards.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 9 "persistidos, com integrações externas simuladas." (EN: persisted, with simulated external integrations.))
- Found: TLS is terminated by Vercel and Supabase; the team cannot insert inspection at the server edge. Client traffic originates from organization workstations.
- Missing: Any in-repo component that performs or controls TLS interception.
- Conclusion: Organization IT/security-testing control (corporate secure web gateway or test proxy). Nothing to implement in the application.

**Recommended Action:**
- Security testing (development/testing phase): testers may use Burp Suite or mitmproxy on an isolated test machine against staging deployments with demo data only, to inspect API and Supabase calls (auth flows, RLS bypass attempts, Realtime messages). Remove the test root CA from the trust store and securely delete captures afterwards.
- Corporate gateway: if the organization's IT runs TLS inspection on clinician workstations, obtain legal/privacy approval (HIPAA/GDPR), store the inspection CA key in an HSM, and consider bypassing inspection for `*.supabase.co` and the ACME Clinical domains if real patient data is ever used, so PHI is not decrypted and logged by the gateway.
- Do not pin certificates in the frontend in a way that breaks with the gateway unless agreed with IT; do not disable TLS validation in the backend's HTTP client to "work with" a proxy.
- Turn inspection off when not actively needed.

**Status:** Documented
