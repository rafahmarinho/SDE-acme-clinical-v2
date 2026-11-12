---
name: t2142-verify-that-function-level-authorization-is-implem
description: Verify with automated tests and code review that every ACME Clinical API function, especially administrative ones (staff roles, simulation reset, alarm limits), is denied by default and allowed only for explicitly permitted roles.
---

# T2142: Verify that function level authorization is implemented in API

**Category:** CODE_FIX
**SD Elements:** [T2142](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2142/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you can create something very visual in 3D if")
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Teams test that administrators can manage staff, but not that a nurse calling the same endpoint is rejected. The SD Elements guidance mentions Spring's `.anyRequest().denyAll()`; this stack is FastAPI, so the equivalent is the startup guard plus per-route `require()` dependencies described in T2141.

**Secure Implementation Pattern:**
```python
# backend/tests/test_function_level_authz.py
from fastapi.routing import APIRoute
from app.main import app
from app.core.security import PUBLIC_ROUTES, PERMISSIONS, Role

def route_perm(route: APIRoute):
    for d in route.dependant.dependencies:
        if p := getattr(d.call, "__perm__", None):
            return p
    return None

def test_every_mutating_route_has_permission():
    missing = [r.path for r in app.routes if isinstance(r, APIRoute)
               and r.path not in PUBLIC_ROUTES
               and r.methods & {"POST", "PUT", "PATCH", "DELETE"}
               and route_perm(r) is None]
    assert missing == []

async def test_admin_functions_denied(client_as):
    for role in (Role.NURSE, Role.PHYSICIAN, Role.BIOMED):
        c = client_as(role)
        assert (await c.post("/simulation/reset")).status_code == 403
        assert (await c.patch("/staff/00000000-0000-0000-0000-000000000001/role",
                              json={"role": "administrator"})).status_code == 403
```

**Implementation Guidance:**
- Check 1 (abstract controller): `admin_router()`/`require()` exist in `backend/app/routers/_base.py` and `backend/app/core/security.py`.
- Check 2 (inheritance): `staff.py`, simulation reset and audit routes are created via `admin_router(...)`.
- Check 3 (admin functions in regular controllers): threshold writes, device deletion and monitor binding carry explicit `require(...)`.
- Check 4 (deny by default): introspect `app.routes` as above; also test HTTP method tampering (e.g. `DELETE` on a GET-only path returns 405, not success).
- Exercise each endpoint with each role and with a forged `role` field in the request body to confirm it is ignored.
- Reference: SD Elements guidance for T2142.

**Success Criteria:**
- [ ] `test_every_mutating_route_has_permission` passes and is in CI.
- [ ] Non-admin roles receive 403 for all administrative functions.
- [ ] Request bodies containing `role`/`is_admin` do not change authorization outcome.

**Status:** Applied
