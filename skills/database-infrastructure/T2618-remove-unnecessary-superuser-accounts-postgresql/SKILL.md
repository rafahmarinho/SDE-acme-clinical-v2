---
name: t2618-remove-unnecessary-superuser-accounts-postgresql
description: Ensure no unnecessary login-capable superuser or highly privileged roles exist for ACME Clinical's Supabase PostgreSQL and that the backend uses a least-privilege role instead of postgres or service_role.
---

# T2618: Remove unnecessary superuser accounts (PostgreSQL) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2618](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2618/)
**Priority:** 6/10 · **Phase:** deployment

**Guidance:** Find login-capable superusers with `SELECT rolname FROM pg_authid WHERE rolsuper and rolcanlogin;`, remove superuser with `ALTER USER ... NOSUPERUSER` or revoke inherited roles; optionally use `set_user` for logged privilege escalation instead of direct superuser login.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 37 "Tenha perfis de enfermeiro, médico, técnico biomédico e administrador" (EN: "Have nurse, physician, biomedical technician and administrator profiles"))
- Found: hosted Supabase PostgreSQL. The PRD's "administrador" is an application role (Supabase Auth user), not a database superuser.
- Missing: Supabase reserves its own internal superuser (`supabase_admin`) and the customer `postgres` role; these cannot be removed by the project.
- Conclusion: Mainly a platform/ops check. The repo should never create superuser or `bypassrls` roles in `supabase/migrations/`; app roles (e.g. `acme_api`) should be `nosuperuser nocreaterole nocreatedb` with grants limited to required tables.

**Recommended Action:** Platform owner: (1) run `select rolname, rolsuper, rolbypassrls from pg_roles where rolcanlogin;` and confirm only Supabase-managed roles are privileged; (2) ensure no custom role has `superuser` or `bypassrls`; (3) restrict who holds the `postgres` password and the `service_role` key, and keep the latter server-side only; (4) review the list each release and when staff change.

**Status:** Documented
