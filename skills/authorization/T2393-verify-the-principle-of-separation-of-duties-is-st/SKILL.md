---
name: t2393-verify-the-principle-of-separation-of-duties-is-st
description: Verify that no ACME Clinical role or user holds conflicting duties (granting privileges, custody of monitors, recording clinical actions, verifying audit) and that two-person rules for privileged role changes cannot be bypassed.
---

# T2393: Verify the principle of Separation of Duties is strongly implemented

**Category:** CODE_FIX
**SD Elements:** [T2393](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2393/)
**Priority:** 9/10 · **Phase:** testing

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
With four roles and no explicit SoD review, privileges creep (e.g. "give admins everything for the demo"). Nothing would detect that one account can grant itself rights, act clinically and then edit the record of what it did.

**Secure Implementation Pattern:**
```python
# backend/tests/test_separation_of_duties.py
from app.core.security import PERMISSIONS, Perm, Role

CONFLICTS = [  # pairs that must never coexist in one role
    {Perm.STAFF_MANAGE, Perm.ALARM_ACK},
    {Perm.STAFF_MANAGE, Perm.THRESHOLD_WRITE},
    {Perm.MONITOR_BIND, Perm.ALARM_ACK},
    {Perm.STAFF_MANAGE, Perm.AUDIT_WRITE},
]

def test_no_role_holds_conflicting_permissions():
    for role, perms in PERMISSIONS.items():
        for pair in CONFLICTS:
            assert not pair <= perms, f"{role} holds conflicting {pair}"

async def test_self_promotion_blocked(client_as, admin_a):
    r = await client_as(admin_a).patch(f"/staff/{admin_a.id}/role", json={"role": "physician"})
    assert r.status_code == 403

async def test_two_person_rule(client_as, admin_a, admin_b, nurse):
    req = (await client_as(admin_a).post(f"/staff/{nurse.id}/role-requests",
                                         json={"role": "administrator"})).json()
    assert (await client_as(admin_a).post(f"/role-requests/{req['id']}/approve")).status_code == 403
    assert (await client_as(admin_b).post(f"/role-requests/{req['id']}/approve")).status_code == 200
```

**Implementation Guidance:**
- Encode the conflict pairs from T2388 in the test and run it against `PERMISSIONS` in `backend/app/core/security.py`; also check the SQL `role_permissions` seed in `supabase/seed.sql` matches.
- Review user-to-role assignments: a staff row has exactly one role (DB constraint), so a user cannot accumulate roles.
- Verify two-person approval, no self-approval, and that the role-change audit row records requester and approver.
- Verify audit records cannot be modified by any application role (pgTAP in `supabase/tests/`).
- Reference: SD Elements guidance for T2393.

**Success Criteria:**
- [ ] Conflict test passes and fails if a conflicting permission is added.
- [ ] Self-promotion and self-approval return 403.
- [ ] `staff.role` is a single non-null enum column; audit table is append-only.

**Status:** Applied
