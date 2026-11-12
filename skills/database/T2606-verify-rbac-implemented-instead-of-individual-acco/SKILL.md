---
name: t2606-verify-rbac-implemented-instead-of-individual-acco
description: Verify with pgTAP tests that ACME Clinical database access is granted through group roles and the role_permissions matrix, with default deny for anon/authenticated/public and granular per-operation privileges.
---

# T2606: Verify RBAC implemented instead of individual accounts

**Category:** CODE_FIX
**SD Elements:** [T2606](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2606/)
**Priority:** 10/10 · **Phase:** testing

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
Without verification, ad-hoc grants added while debugging (e.g. `grant all on all tables in schema public to anon`) persist into the demo deployment and nobody notices.

**Secure Implementation Pattern:**
```sql
-- supabase/tests/rbac.sql (run with `supabase test db`)
begin;
select plan(5);

select is((select count(*)::int from information_schema.role_table_grants
           where table_schema in ('clinical','devices','simulation','audit','security')
             and grantee in ('anon','public')), 0, 'anon/public have no table grants');

select is((select count(*)::int from information_schema.role_table_grants g
           join pg_roles r on r.rolname = g.grantee
           where r.rolcanlogin and g.grantee not in ('postgres','authenticated')
             and g.table_schema in ('clinical','devices','simulation','audit')), 0,
          'no grants directly to login roles');

-- impersonate a nurse via JWT claims
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"00000000-0000-0000-0000-0000000000a1"}', true);
select ok(not public.has_permission('threshold:write'), 'nurse cannot write thresholds');
select ok(public.has_permission('alarm:ack'), 'nurse can ack alarms');
select set_config('request.jwt.claims', '{"sub":"00000000-0000-0000-0000-0000000000ff"}', true); -- role null
select is((select count(*)::int from clinical.patients), 0, 'unassigned staff sees nothing');
select * from finish();
rollback;
```

**Implementation Guidance:**
- Seed fixed test users per role in `supabase/seed.sql` (fictional, demo-only) for pgTAP.
- Check default deny: no grants to `public`/`anon`; `authenticated` only gets the grants RLS needs.
- Check that privileges are attached to NOLOGIN group roles, and login roles only via membership (`pg_auth_members`).
- Compare `security.role_permissions` with `backend/app/core/security.py` (Python test reading both).
- Reference: SD Elements guidance for T2606.

**Success Criteria:**
- [ ] `supabase test db` passes the RBAC suite in CI.
- [ ] Granularity: each role has only the permissions listed in the matrix (exact-set assertion).
- [ ] Python/SQL matrix parity test passes.

**Status:** Pending
