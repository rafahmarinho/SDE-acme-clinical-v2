---
name: t2277-test-to-confirm-the-use-of-an-account-and-identity
description: Test suite and checklist confirming that ACME Clinical's Supabase-based team management can add, modify, disable, reactivate and remove staff and service accounts, assign roles and account managers, monitor usage, support reviews and leave no default accounts, verifying T340.
---

# T2277: Test to confirm the use of an account and identity management system

**Category:** CODE_FIX
**SD Elements:** [T2277](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2277/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe"
> (EN: limit settings, reports and team management)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
A team list screen can look finished while lacking disable, role-change or review capabilities, or while leaving public sign-up and demo default accounts active. This suite checks each account-management capability.

**Secure Implementation Pattern:**
```python
# backend/tests/test_account_management.py
import pytest

async def test_full_lifecycle(admin_client, fake_admin_api):
    r = await admin_client.post("/admin/staff", json={"email": "new.tech@acme.test",
        "full_name": "New Tech", "role": "biomedical_technician", "employee_number": "E900"})
    uid = fake_admin_api.last_created_id
    assert (await admin_client.patch(f"/admin/staff/{uid}", json={"role": "nurse"})).status_code == 200
    assert fake_admin_api.users[uid]["app_metadata"]["role"] == "nurse"
    assert (await admin_client.post(f"/admin/staff/{uid}/disable")).status_code == 204
    assert fake_admin_api.users[uid]["ban_duration"] != "none"
    assert (await admin_client.post(f"/admin/staff/{uid}/reactivate")).status_code == 204
    assert (await admin_client.delete(f"/admin/staff/{uid}")).status_code == 204

async def test_account_manager_recorded(admin_client, db):
    row = await db.fetchrow("select created_by from profiles where email='new.tech@acme.test'")
    assert row["created_by"] is not None

@pytest.mark.parametrize("role", ["nurse", "physician", "biomedical_technician"])
async def test_non_admin_cannot_manage(client_as, role):
    r = await client_as(role).post("/admin/staff", json={})
    assert r.status_code == 403

def test_public_signup_disabled(supabase_config):
    assert supabase_config["auth"]["enable_signup"] is False
```

**Implementation Guidance:**
- Map each T2277 question to a test or a documented answer:
  - Add, remove, disable, modify, activate: lifecycle test.
  - Account types: role enum plus the service account inventory in the README.
  - Account managers: `created_by` and audit log.
  - Authenticators: password policy (T4) and TOTP MFA (T1).
  - Roles and permissions: RLS and `require_role` tests.
  - Creation approval: admin aal2 only.
  - Usage monitoring and notification: `last_sign_in_at` inactive-account report plus login notifications (T427).
  - Access authorization: deny-by-default RLS test.
  - Compliance review: `/admin/staff/review` (T233).
  - Shared credentials: none by design (T135).
  - Default authenticators: T323 test.
- Run the RLS deny-by-default check: an authenticated user without a role can read no clinical table.
- Manual: walk through the Team Management screen as an administrator, and confirm that a disabled user is logged out within one token lifetime (shorten `jwt_expiry` to at most 3600 seconds).
- Reference: SD Elements guidance for T2277.

**Success Criteria:**
- [ ] The lifecycle, permission and config tests pass in CI.
- [ ] A checklist in the test report answers every T2277 question with a linked test or evidence, and none is answered "no".

**Status:** Applied
