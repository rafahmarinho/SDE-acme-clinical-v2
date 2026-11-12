---
name: t2274-test-to-confirm-that-the-principle-of-least-privil
description: Automated tests proving ACME Clinical roles, ward assignments and the database account hold only minimum privileges, receive them only when assigned, and lose them immediately on deactivation or role change.
---

# T2274: Test to confirm that the principle of least privilege is strongly implemented

**Category:** CODE_FIX
**SD Elements:** [T2274](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2274/)
**Priority:** 9/10 · **Phase:** testing

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
Without dedicated tests, teams usually verify only that each role can do its job ("happy path"), never that it cannot do more. Over-broad permissions (e.g. a biomedical technician editing alarm limits, a deactivated nurse still streaming vitals) go unnoticed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_least_privilege.py
import pytest
from app.core.security import PERMISSIONS, Perm, Role

ENDPOINTS = {  # every protected route -> required permission
    ("POST", "/alarms/{id}/ack"): Perm.ALARM_ACK,
    ("PUT", "/thresholds/{id}"): Perm.THRESHOLD_WRITE,
    ("POST", "/monitors/{id}/bind"): Perm.MONITOR_BIND,
    ("PATCH", "/staff/{id}/role"): Perm.STAFF_MANAGE,
    ("POST", "/simulation/reset"): Perm.SIM_RESET,
}

@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("route,perm", ENDPOINTS.items())
async def test_restricted(client_as, role, route, perm, ids):
    method, path = route
    r = await client_as(role).request(method, path.format(id=ids[path]), json={})
    expected_denied = perm not in PERMISSIONS[role]
    assert (r.status_code in (403, 404)) == expected_denied

async def test_revoked_immediately(client_as, admin, nurse):
    await admin.patch(f"/staff/{nurse.id}", json={"active": False})
    r = await client_as(nurse).get("/patients")       # same, still unexpired JWT
    assert r.status_code == 401

async def test_granted_late(client_as, new_staff):
    assert (await client_as(new_staff).get("/patients")).status_code == 403
```

**Implementation Guidance:**
- Maintain a route inventory (`ENDPOINTS`) and add a meta-test that fails when `app.routes` contains a route not listed, so new endpoints cannot skip the matrix.
- "Restricted as much as possible": assert each role is denied every permission not explicitly in its set, plus cross-ward object access (nurse in Ward A vs patient in Ward B).
- "Granted as late as possible": a newly invited staff account without role/ward cannot read patients; break-glass (T337) grants expire.
- "Revoked as soon as possible": deactivation and role changes apply on the next request; Realtime channel subscriptions for revoked users are refused by RLS.
- Add a SQL test (`supabase/tests/least_privilege.sql`, pgTAP) asserting `acme_api` has no `DELETE`, `TRUNCATE`, DDL, `SUPERUSER` or `BYPASSRLS`.
- Reference: SD Elements guidance for T2274.

**Success Criteria:**
- [ ] Role x endpoint matrix test passes in CI and fails if a permission is widened without updating expectations.
- [ ] Revocation test passes using an unexpired token after deactivation.
- [ ] pgTAP check of `acme_api` privileges passes.

**Status:** Applied
