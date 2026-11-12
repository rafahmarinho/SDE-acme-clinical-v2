---
name: t2661-change-insecure-configuration-defaults-and-remove
description: Harden ACME Clinical's Supabase PostgreSQL project beyond its defaults by disabling unused extensions and APIs, restricting connectivity, avoiding the postgres superuser for the app, and creating least-privilege database roles.
---

# T2661: Change insecure configuration defaults and remove unnecessary features (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2661](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2661/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** Treat default database configurations as development-only. Before production: disable unnecessary features/plugins, restrict connectivity (ports), remove test databases, remove or rename default administrator accounts, require secure authentication, create limited-permission users and tighten other permissive settings.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 47 "Entregue o código completo, configuração do banco, dados iniciais" (EN: "Deliver the complete code, database configuration, initial data"))
- Found: hosted Supabase PostgreSQL; the PRD asks for database configuration and seed data to be delivered with the code.
- Missing: access to server configuration (`postgresql.conf`, ports, default `postgres` account) which Supabase manages.
- Conclusion: Mostly platform settings. Part can be expressed in the repo: `supabase/migrations/0001_schema.sql` can create a least-privilege `acme_api` role (as already assumed by `DATABASE_URL` in `backend/.env.example`), enable RLS on every table, revoke default grants from `anon`/`public`, and enable only required extensions. `supabase/seed.sql` demo data (12 fictional patients, 10 monitors) must not be loaded into a production project unless that project is explicitly the demo.

**Recommended Action:** Platform owner in the Supabase Dashboard: (1) Database > Extensions: disable extensions not used by the app; (2) API settings: expose only the schemas the frontend needs and keep `graphql_public` disabled if unused; (3) Database > Network Restrictions and SSL enforcement on; (4) rotate the `postgres` password to a strong secret held only by admins and never put it in Vercel env vars; use the dedicated `acme_api` role and the service-role key server-side only; (5) Auth settings: disable unused providers, enable email confirmation and leaked-password protection; (6) run Supabase Advisors (security) and resolve findings before go-live.

**Status:** Documented
