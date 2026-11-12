---
name: t74-avoid-http-parameter-pollution
description: Prevents HTTP parameter pollution in ACME Clinical search and filter endpoints by rejecting duplicated query parameters unless explicitly modeled as lists, so FastAPI, Vercel and the frontend interpret parameters identically.
---

# T74: Avoid HTTP parameter pollution

**Category:** CODE_FIX
**SD Elements:** [T74](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T74/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: "filters, loading states and error messages. Adapt navigation to user profiles")
> Source: specs/PRD.md, line 13

**What the spec implies (naive approach):**
Filters (ward, alarm status, device state, date range) will be query parameters. FastAPI takes the last value of a repeated scalar parameter, while other layers (Vercel firewall rules, logging, frontend URL parsing) may take the first or join them, so `?ward=A&ward=B` can bypass a check applied to one value but enforced on another.

**Secure Implementation Pattern:**
```python
# backend/app/main.py
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

MULTI_ALLOWED = {"status", "ward_id"}   # params explicitly modeled as list[...]

class RejectDuplicateParams(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        keys = [k for k, _ in request.query_params.multi_items()]
        dups = {k for k in keys if keys.count(k) > 1 and k not in MULTI_ALLOWED}
        if dups:
            return JSONResponse({"error": "Invalid request."}, status_code=400)
        return await call_next(request)

app.add_middleware(RejectDuplicateParams)

# routers/alarms.py - explicit, validated list
from typing import Annotated
from fastapi import Query
@router.get("/alarms")
async def list_alarms(status: Annotated[list[AlarmStatus], Query(max_length=5)] = [],
                      ward_id: Annotated[list[UUID], Query(max_length=10)] = []):
    ...
```

**Implementation Guidance:**
- Validate inside the application (FastAPI/Pydantic) rather than relying on an external filter; that is the primary defense.
- Reject duplicated scalar query parameters in middleware; parameters intended to repeat must be declared as typed, bounded `list[...]`.
- In the frontend (`frontend/src/services`), build query strings with `URLSearchParams` and never concatenate user text into URLs.
- Do not mix query and body sources for the same field; read each field from one place only.
- Reference: SD Elements guidance for T74.

**Success Criteria:**
- [ ] `GET /api/patients?search=a&search=b` returns 400.
- [ ] `GET /api/alarms?status=active&status=acknowledged` works and each value is enum-validated.
- [ ] Test confirms a polluted payload split across duplicates (`q=<scr&q=ipt>`) is rejected.

**Status:** Pending
