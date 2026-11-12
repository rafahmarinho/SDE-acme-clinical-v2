---
name: t350-verify-that-audit-information-is-sufficiently-prot
description: Tests that ACME Clinical audit_events cannot be updated or deleted by any app role (including via the simulation reset), are readable only per RLS policy, and that tampering attempts are themselves recorded.
---

# T350: Verify that audit information is sufficiently protected

**Category:** CODE_FIX
**SD Elements:** [T350](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T350/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: choose scenarios, advance the simulation, view events and reset the data. The results)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
"Reiniciar os dados" invites a `TRUNCATE` of every table including the events/audit table, and the Supabase anon key with permissive RLS lets any logged-in user `update`/`delete` audit rows from the browser. Audit records would be neither append-only nor trustworthy.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql (control under test)
alter table public.audit_events enable row level security;
revoke update, delete, truncate on public.audit_events from anon, authenticated, service_role;
create policy audit_read on public.audit_events for select to authenticated
  using ((auth.jwt() -> 'app_metadata' ->> 'role') in ('admin','physician'));
create or replace function public.block_audit_mutation() returns trigger language plpgsql as $$
begin raise exception 'audit_events is append-only'; end $$;
create trigger audit_no_update before update or delete on public.audit_events
  for each row execute function public.block_audit_mutation();
```
```python
# backend/tests/test_audit_protection.py
import pytest
from postgrest.exceptions import APIError

def test_authenticated_user_cannot_modify_audit(supabase_as_admin_user):
    with pytest.raises(APIError):
        supabase_as_admin_user.table("audit_events").update({"outcome": "success"}).eq("id", 1).execute()
    with pytest.raises(APIError):
        supabase_as_admin_user.table("audit_events").delete().eq("id", 1).execute()

def test_nurse_cannot_read_audit(supabase_as_nurse):
    assert supabase_as_nurse.table("audit_events").select("*").execute().data == []

def test_simulation_reset_preserves_audit(api_client, admin_token, audit_count):
    before = audit_count()
    api_client.post("/simulation/reset", headers={"Authorization": f"Bearer {admin_token}"})
    assert audit_count() == before + 1        # reset itself is audited, history kept
```

**Implementation Guidance:**
- Run against the Supabase local stack (`supabase start`) with real user JWTs for each role, plus a direct SQL session as `service_role`.
- Attempt UPDATE, DELETE, TRUNCATE on `audit_events` (and `security_events`) for every role; expect failure.
- Verify read access matches policy (decide which roles view "eventos"; nurses may see clinical event view but not raw security audit) and is read-only.
- Verify `services/simulation.py` reset excludes audit tables and logs `simulation.reset`.
- Verify Storage-exported audit reports (if any) are in a private bucket and immutable to non-admins.
- WORM storage is not offered in this stack; document that append-only enforcement is via grants + trigger, with hash chaining (T485) to detect tampering by DB owners.
- Reference: SD Elements guidance for T350.

**Success Criteria:**
- [ ] All modification attempts fail for anon, authenticated and service_role.
- [ ] Unauthorized roles get zero audit rows.
- [ ] Simulation reset leaves prior audit rows intact and adds one reset event.

**Status:** Pending
