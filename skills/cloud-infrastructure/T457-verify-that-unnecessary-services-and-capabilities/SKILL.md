---
name: t457-verify-that-unnecessary-services-and-capabilities
description: Verify that ACME Clinical's inventory of enabled Vercel and Supabase capabilities (auth providers, exposed schemas, extensions, buckets, functions, ports, integrations) is complete and that every item marked unnecessary is actually disabled.
---

# T457: Verify that unnecessary services and capabilities are disabled (NON-CODE)

**Category:** INFRA
**SD Elements:** [T457](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T457/)
**Priority:** 6/10 · **Phase:** testing

**Guidance:** Ensure the list of components and capabilities (functions, services, protocols, ports) is complete and current, and test that every capability marked unnecessary is disabled; otherwise the test fails.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "...Supabase para PostgreSQL, login por e-mail e" (EN: ...Supabase for PostgreSQL, email login and...) and line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.))
- Found: Required Supabase capabilities are PostgreSQL, email/password Auth, Storage and Realtime; Vercel hosts the frontend and API.
- Missing: Verification targets provider settings configured per T456.
- Conclusion: Manual/operational verification with scriptable probes.

**Recommended Action:**
Checklist (fail on any unexpected item):
- [ ] Inventory from T456 exists and was reviewed within the last quarter.
- [ ] Supabase Auth: only Email provider enabled; anonymous sign-in off; `POST /auth/v1/signup` behaves as documented (disabled or CAPTCHA-protected).
- [ ] `select extname from pg_extension` matches the inventory; `pg_graphql` absent or justified.
- [ ] `GET /rest/v1/` with the anon key reveals only intended schemas/tables; Security Advisor shows no "RLS disabled" findings.
- [ ] Storage buckets list matches inventory; none public.
- [ ] Realtime publication contains only intended tables.
- [ ] `nmap` on frontend/API domains: only 80/443.
- [ ] Vercel: Preview deployments require authentication; Integrations list matches inventory; build logs/source protection enabled.
- [ ] FastAPI `/docs` and `/openapi.json` disabled or protected in production.

**Status:** Documented
