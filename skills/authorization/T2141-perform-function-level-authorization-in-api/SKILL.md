---
name: t2141-perform-function-level-authorization-in-api
description: Enforce deny-by-default, function-level authorization on every ACME Clinical FastAPI endpoint, with an administrative router base that requires administrator permissions for staff management and simulation reset.
---

# T2141: Perform function level authorization in API

**Category:** CODE_FIX
**SD Elements:** [T2141](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T2141/)
**Priority:** 8/10 · **Phase:** architecture-design

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you can create something very visual in 3D if")
> Source: specs/PRD.md, line 27

> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: "choose scenarios, advance the simulation, view events and reset the data. The results")
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
Staff management, threshold configuration and the "reset data" action would be implemented as regular authenticated endpoints. Any logged-in user who discovers `POST /simulation/reset` or `PATCH /staff/{id}/role` could wipe data or promote themselves.

**Secure Implementation Pattern:**
```python
# backend/app/routers/_base.py  ("abstract controller" equivalents)
from fastapi import APIRouter, Depends
from app.core.security import get_current_user, require, Perm

def protected_router(**kw) -> APIRouter:
    # Every route requires authentication; individual routes add require(...)
    return APIRouter(dependencies=[Depends(get_current_user)], **kw)

def admin_router(perm: Perm, **kw) -> APIRouter:
    return APIRouter(dependencies=[Depends(require(perm))], **kw)

# backend/app/routers/staff.py
router = admin_router(Perm.STAFF_MANAGE, prefix="/staff", tags=["staff"])

@router.patch("/{staff_id}/role")
async def change_role(staff_id: UUID, body: RoleChange, user=Depends(require(Perm.STAFF_MANAGE))): ...

# backend/app/main.py -- deny by default: fail startup if a route lacks a permission dependency
for r in app.routes:
    if isinstance(r, APIRoute) and r.path not in PUBLIC_ROUTES:
        deps = {d.call for d in r.dependant.dependencies}
        if not any(getattr(d, "__perm__", None) or d is get_current_user for d in deps):
            raise RuntimeError(f"Route {r.path} has no authorization dependency")
```

**Implementation Guidance:**
- Create `protected_router()` and `admin_router()` factories in `backend/app/routers/_base.py`; administrative routers (`staff.py`, simulation reset in `simulation.py`, audit) must be built from `admin_router` ("inherit the administrative controller").
- Regular routers that expose an administrative function (e.g. `thresholds.py` PUT, `devices.py` DELETE) add an explicit `Depends(require(Perm.X))` on that operation.
- Tag `require()` checkers with a `__perm__` attribute and add the startup guard in `backend/app/main.py` so a route without an authorization dependency fails to boot (deny by default).
- Return 403 for authenticated-but-forbidden, 401 for unauthenticated; never rely on the frontend hiding the button.
- Reference: SD Elements guidance for T2141.

**Success Criteria:**
- [ ] App startup fails in a test that registers a route without an authorization dependency.
- [ ] Nurse, physician and biomedical technician get 403 on `POST /simulation/reset` and `PATCH /staff/{id}/role`.
- [ ] All `POST/PUT/PATCH/DELETE` routes carry an explicit `require(...)`.

**Status:** Pending
