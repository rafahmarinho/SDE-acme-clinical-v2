---
name: t32-always-perform-input-validation-on-a-server
description: Ensures ACME Clinical validates input on the FastAPI server (and in Supabase constraints) in addition to the React forms, uses identical rules on both sides, returns generic errors and logs server-side rejections as security events.
---

# T32: Always perform input validation on a server

**Category:** CODE_FIX
**SD Elements:** [T32](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T32/)
**Priority:** 7/10 · **Phase:** architecture-design

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: "filters, loading states and error messages. Adapt navigation to user profiles")
> Source: specs/PRD.md, line 13

**What the spec implies (naive approach):**
Forms with error messages suggest validation in React (e.g. `min`/`max` on inputs). Because the frontend can also talk directly to Supabase, a developer may rely solely on client checks; anyone can bypass them with a proxy or by calling the API/PostgREST directly.

**Secure Implementation Pattern:**
```python
# backend/app/core/errors.py
import logging
from datetime import datetime, timezone
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

security_log = logging.getLogger("acme.security")

async def validation_handler(request: Request, exc: RequestValidationError):
    security_log.warning("input_validation_failed", extra={
        "ts": datetime.now(timezone.utc).isoformat(),
        "ip": request.client.host if request.client else None,
        "route": request.url.path,
        "user_id": getattr(request.state, "user_id", None),
        "fields": [".".join(map(str, e["loc"])) for e in exc.errors()],  # no values
        "code": "VALIDATION_422",
    })
    return JSONResponse(status_code=422, content={"error": "Invalid request."})

# main.py: app.add_exception_handler(RequestValidationError, validation_handler)
```
```sql
-- supabase/migrations/0001_schema.sql: last line of defense
alter table alarm_limits add constraint hr_range check (hr_low between 20 and 250 and hr_high between 20 and 250 and hr_low < hr_high);
alter table observations add constraint text_len check (char_length(text) between 1 and 2000);
```

**Implementation Guidance:**
- Treat FastAPI Pydantic models as the source of truth; mirror the same rules in the React forms (e.g. zod schemas in `frontend/src/lib`) so a server-side failure signals tampering.
- Route all writes through the backend, or, where the frontend writes to Supabase directly, enforce the same rules with CHECK constraints and RLS.
- Return a general error message; field hints may be given to the UI without echoing input or internals.
- Log failures (timestamp, source IP, event, error code) to `backend/app/core/logging.py`; count repeated failures per user and flag them as security incidents (AppSensor-style), optionally throttling the account.
- Reference: SD Elements guidance for T32.

**Success Criteria:**
- [ ] Every write endpoint rejects invalid data when called directly (bypassing the UI) with 422 and a generic message.
- [ ] Direct Supabase inserts violating ranges fail on CHECK constraints.
- [ ] Validation failure log entries include timestamp, IP, route and error code, with no submitted values.

**Status:** Pending
