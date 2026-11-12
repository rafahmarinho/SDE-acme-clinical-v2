---
name: t18-make-authorization-decisions-using-full-context
description: Propagate the full ACME Clinical security context (user id, role, ward assignments, break-glass grants) from FastAPI routers into services and into PostgreSQL via JWT claims so every layer, including RLS, can make correct authorization decisions.
---

# T18: Make authorization decisions using full context

**Category:** CODE_FIX
**SD Elements:** [T18](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T18/)
**Priority:** 9/10 · **Phase:** architecture-design

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: "ward view, patient list and detail, live monitoring, alarms, devices,")
> Source: specs/PRD.md, line 25

> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: "frontend. The generation of readings, alarms and reports must be done in Python. The")
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
Routers check "is logged in", then call services such as `reports.generate(patient_id)` that only receive IDs. The service and the database (connected with a privileged key) have no idea who the user is or which ward they work in, so they cannot refuse cross-ward access.

**Secure Implementation Pattern:**
```python
# backend/app/db.py -- pass the end-user context into PostgreSQL for RLS
from contextlib import asynccontextmanager
import json

@asynccontextmanager
async def user_tx(pool, user: CurrentUser):
    async with pool.acquire() as conn, conn.transaction():
        claims = {"sub": str(user.id), "role": "authenticated",
                  "app_role": user.role, "ward_ids": [str(w) for w in user.ward_ids],
                  "break_glass_patient_ids": [str(p) for p in user.break_glass]}
        await conn.execute("set local role authenticated")
        await conn.execute("select set_config('request.jwt.claims', $1, true)", json.dumps(claims))
        yield conn

# backend/app/services/reports.py -- services require the context, not just ids
async def generate_patient_report(user: CurrentUser, patient_id: UUID, pool) -> Report:
    async with user_tx(pool, user) as conn:
        patient = await conn.fetchrow("select * from clinical.patients where id = $1", patient_id)
        if patient is None:                     # filtered by RLS => not visible to this user
            raise NotFound()
        ...
```

**Implementation Guidance:**
- Every service function in `backend/app/services/*.py` takes `user: CurrentUser` as its first argument; no service is callable with only an ID.
- Build `CurrentUser` once per request in `backend/app/core/security.py` (role, wards, active break-glass grants) and pass it down explicitly (no global/thread-local state; see T205).
- In `backend/app/db.py`, set `request.jwt.claims` with `set_config(..., true)` (transaction-local) so Supabase RLS policies using `auth.uid()` and custom claims apply to API queries too.
- Background jobs (simulation ticks, report rendering) run as a dedicated service identity with its own narrow permissions, recorded in audit as `actor=system:simulator`.
- Reference: SD Elements guidance for T18.

**Success Criteria:**
- [ ] Calling a service with a nurse context for another ward's patient raises NotFound even if the router check is removed (unit test).
- [ ] RLS policies are exercised in API queries (test with RLS-only rule blocks access).
- [ ] Transaction-local claims do not leak between pooled connections (test two sequential users on one connection).

**Status:** Applied
