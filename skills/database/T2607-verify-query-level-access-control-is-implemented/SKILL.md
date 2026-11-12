---
name: t2607-verify-query-level-access-control-is-implemented
description: Verify ACME Clinical database roles reach only the schemas, tables, columns and functions they need, e.g. biomedical technicians and the simulator cannot read clinical notes, staff cannot write role columns, and only the reset function can delete demo data.
---

# T2607: Verify query-level access control is implemented

**Category:** CODE_FIX
**SD Elements:** [T2607](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2607/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow binding a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Table-wide grants such as `grant all on all tables in schema public to authenticated` would let any logged-in user (or the simulator) read observation notes, update `staff.role`, or call the reset function directly via PostgREST RPC.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0004_column_grants.sql
revoke update on public.staff from authenticated;
grant update (display_name, phone, preferences) on public.staff to authenticated; -- profile only
revoke update on clinical.alarms from authenticated, acme_api_rw;
grant update (acknowledged_at, acknowledged_by, ack_note) on clinical.alarms to acme_api_rw;
-- alarm state/condition columns are written only by the Python alarm engine function
revoke execute on all functions in schema simulation from public, anon, authenticated;

-- supabase/tests/query_level.sql
begin; select plan(5);
select ok(not has_column_privilege('authenticated','public.staff','role','UPDATE'), 'no self role edit');
select ok(not has_column_privilege('acme_api_rw','clinical.alarms','condition_active','UPDATE'),
          'ack cannot clear an active condition');
select ok(not has_table_privilege('acme_sim_rw','clinical.observations','SELECT'), 'simulator cannot read notes');
select ok(not has_function_privilege('authenticated','simulation.reset_demo_data(uuid)','EXECUTE'),
          'reset not callable via PostgREST');
select ok(not has_table_privilege('anon','clinical.vital_readings','SELECT'), 'anon cannot read vitals');
select * from finish(); rollback;
```

**Implementation Guidance:**
- Build an access inventory: for each role (`anon`, `authenticated`, `acme_api_rw`, `acme_sim_rw`, `acme_reporting`) list the tables/columns/functions it needs and assert everything else is denied.
- Use column-level grants for sensitive columns: `staff.role`, `staff.active`, `alarms.condition_active`, `alarm_thresholds.*`.
- Exposed schemas: in Supabase settings expose only `public` (and possibly an `api` schema of views) to PostgREST; keep `clinical`, `security`, `simulation`, `audit` unexposed.
- Functions: `revoke execute ... from public` by default (PostgreSQL grants EXECUTE to PUBLIC on new functions).
- Run `supabase test db` in CI.
- Reference: SD Elements guidance for T2607.

**Success Criteria:**
- [ ] pgTAP query-level suite passes.
- [ ] PostgREST call `rpc/reset_demo_data` as an authenticated user is rejected.
- [ ] Staff cannot change their own role through Supabase client updates.

**Status:** Pending
