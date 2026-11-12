---
name: t166-protect-against-json-hijacking
description: Protect ACME Clinical's JSON API from JSON hijacking by returning only object-rooted application/json responses (paged envelopes, never top-level arrays), requiring bearer-token authentication rather than ambient cookies, and sending nosniff.
---

# T166: Protect against JSON hijacking

**Category:** CODE_FIX
**SD Elements:** [T166](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T166/)
**Priority:** 7/10 · **Phase:** development

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
List endpoints for patients, alarms and devices are naturally written as `response_model=list[PatientOut]`, returning a bare JSON array. If such an endpoint were ever authenticated by an ambient cookie, a hostile page could include it via `<script src>` and, on legacy browsers, read the array. Mis-typed responses (`text/html`) also enable content sniffing.

**Secure Implementation Pattern:**
```python
# backend/app/schemas/__init__.py
from typing import Generic, TypeVar
T = TypeVar("T")

class Page(Strict, Generic[T]):
    items: list[T]            # arrays are always wrapped in an object
    total: int
    limit: int
    offset: int

# backend/app/routers/alarms.py
@router.get("", response_model=Page[AlarmOut])
async def list_alarms(principal: Principal = Depends(require(Perm.alarms_read)), ...):
    rows, total = await _list(principal, limit, offset)
    return Page(items=rows, total=total, limit=limit, offset=offset)

# backend/app/core/middleware.py - SECURITY_HEADERS (every API response)
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
                    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"}
```
```ts
// frontend/src/services/api.ts - credentials travel only in the Authorization header
const res = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${token}` }, credentials: "omit" });
```

**Implementation Guidance:**
- Every collection endpoint in `backend/app/routers/*.py` uses `response_model=Page[...]` (or another object wrapper); no `response_model=list[...]` at the top level.
- All responses are `application/json` (FastAPI `JSONResponse`); the CSV export in `backend/app/routers/reports.py` is `text/csv` with `Content-Disposition: attachment`.
- Authenticate API calls with the Supabase access token in the `Authorization` header (`backend/app/core/security.py` `get_principal`), never with cookies the browser attaches automatically; the frontend uses `credentials: "omit"` (T29).
- Keep `X-Content-Type-Options: nosniff` and `Cache-Control: no-store` in `SECURITY_HEADERS` (`backend/app/core/middleware.py`).
- Unpredictable per-session URLs / comment prefixes are unnecessary when the above hold; document this decision in `docs/security/web-frontend.md`.
- Reference: SD Elements guidance for T166.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_api_security.py`): iterate `app.routes` and assert no route's `response_model` is a bare `list`.
- [ ] Every JSON response has `Content-Type: application/json` and `X-Content-Type-Options: nosniff`.
- [ ] A request carrying only cookies (no `Authorization`) to a data endpoint returns 401.

**Status:** Pending
