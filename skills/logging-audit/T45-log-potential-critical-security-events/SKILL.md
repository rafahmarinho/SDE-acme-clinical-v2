---
name: t45-log-potential-critical-security-events
description: Adds a separate structured security event log in the ACME Clinical FastAPI backend for authentication, authorization denials, validation failures, role/staff changes, data resets, report exports and file uploads.
---

# T45: Log potential critical security events

**Category:** CODE_FIX
**SD Elements:** [T45](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T45/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: threshold settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: loss of connection. Have nurse, physician, biomedical technician and administrator profiles.)
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
The PRD only asks for a clinical "events" view. Developers would log clinical events but not security events: failed JWT validation, 403s on role-restricted routes, Pydantic validation failures, staff role changes or simulation resets would leave no trace.

**Secure Implementation Pattern:**
```python
# backend/app/core/logging.py
import json, logging
from datetime import datetime, timezone

security_log = logging.getLogger("acme.security")   # separate logger / sink

def sec_event(event: str, *, outcome: str, user_id: str | None, ip: str | None, **fields):
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
             "event": event, "outcome": outcome, "user_id": user_id, "ip": ip,
             **{k: str(v)[:200] for k, v in fields.items()}}          # length-capped
    security_log.info(json.dumps(entry))

# backend/app/main.py
from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def on_validation(request, exc):
    sec_event("input_validation_failed", outcome="fail", user_id=getattr(request.state, "user_id", None),
              ip=request.client.host if request.client else None, path=request.url.path,
              fields=[".".join(map(str, e["loc"])) for e in exc.errors()])
    return JSONResponse({"detail": "Invalid request."}, status_code=422)

# backend/app/core/security.py  (inside require_role dependency)
#   sec_event("authz_denied", outcome="fail", user_id=user.id, ip=ip, role=user.role, path=path)
```

**Implementation Guidance:**
- Keep `acme.security` separate from application logs (own logger, JSON format) and also persist high-risk events to a `security_events` table writable only by the service role.
- Always log: login success/failure and password-recovery requests (via Supabase Auth hooks or the backend auth router), invalid/expired JWTs in `core/security.py`, role-based 403s, Pydantic `RequestValidationError`, unhandled exceptions (T159), app start-up/logging init in `main.py`.
- High-risk features to log: staff creation/deletion and role changes (team management), threshold changes, simulation reset (`routers/simulation`), report generation/export (`services/reports.py`), file uploads to Storage, any administrator action.
- Truncate user-supplied values (≤200 chars) and never include confidential data (T46).
- Reference: SD Elements guidance for T45.

**Success Criteria:**
- [ ] Each event type above emits a `acme.security` JSON entry with ts, event, outcome, user_id, ip.
- [ ] Pytest asserts that a 403 role violation, a 422 validation error and a simulation reset each produce a security event.
- [ ] Security events are not mixed into the clinical events stream.

**Status:** Applied
