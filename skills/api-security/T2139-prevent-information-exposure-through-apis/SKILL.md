---
name: t2139-prevent-information-exposure-through-apis
description: Prevent ACME Clinical's API from exposing PHI or internal data beyond what each endpoint and role needs by using explicit Pydantic response models, column-specific SELECTs, role-aware field filtering, a fixed error schema and disabled docs in production.
---

# T2139: Prevent information exposure through APIs

**Category:** CODE_FIX
**SD Elements:** [T2139](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T2139/)
**Priority:** 7/10 · **Phase:** development

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: threshold settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Team management and patient screens are easily backed by `select *` and `return dict(row)`, sending every column (staff email, lockout counters, password-policy metadata, device secret hashes, patient identifiers) to every role and relying on the React screen to hide fields. Unhandled exceptions or the OpenAPI page can also reveal schema and stack traces.

**Secure Implementation Pattern:**
```python
# backend/app/schemas/__init__.py
class StaffOut(Strict):
    id: UUID
    full_name: str
    role: Role
    active: bool
    email: str | None = None          # populated only for administrators

class MonitorOut(Strict):
    id: UUID; serial: str; bed_label: str | None; battery_pct: int; status: str
    # never: secret_hash, last_ip, internal notes

# backend/app/routers/staff.py
STAFF_COLUMNS = "id, full_name, role, active, email"
@router.get("", response_model=Page[StaffOut])
async def list_staff(principal: Principal = Depends(require(Perm.staff_read)), ...):
    rows = await fetch_all(conn, f"select {STAFF_COLUMNS} from public.staff_profiles order by full_name limit %s offset %s",
                           (limit, offset))
    if principal.role is not Role.administrator:
        rows = [{**r, "email": None} for r in rows]
    return Page(items=rows, total=total, limit=limit, offset=offset)
```

**Implementation Guidance:**
- Every route in `backend/app/routers/*.py` declares a `response_model` from `backend/app/schemas/__init__.py`; models use `extra="forbid"` (`Strict`) so unexpected keys fail validation instead of leaking.
- Select explicit columns (no `select *`) in routers and `backend/app/services/*.py`; never return secret hashes (`monitors.secret_hash`), lockout/session internals or audit signatures to non-admin roles.
- Apply role-based field filtering server-side (`backend/app/core/security.py` `Principal.role`) and the column-level grants/RLS in `supabase/migrations/0003_authz_rbac.sql` and `0007_privacy.sql`; the frontend must not be the filter.
- Errors use the single envelope from `backend/app/core/errors.py` (`error_body`): generic message, code, request id; no stack traces, SQL text or upstream bodies.
- Disable `/docs`, `/redoc`, `/openapi.json` in production (`backend/app/main.py`); remove unused endpoints.
- Reference: SD Elements guidance for T2139.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_api_security.py`): every `APIRoute` has a `response_model` (or explicit `Response` class) and none of the models contain fields named `*secret*`, `*hash*`, `password*`.
- [ ] Pytest: nurse calling `GET /staff` receives `email: null`; administrator receives emails.
- [ ] A forced 500 returns only `{"error": {"code", "message", "request_id"}}`; `/openapi.json` returns 404 in production settings.

**Status:** Applied
