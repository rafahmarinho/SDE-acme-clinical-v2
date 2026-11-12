---
name: t159-follow-best-practices-for-secure-error-and-excepti
description: Adds a global FastAPI exception handler and centralized error catalogue for ACME Clinical that returns generic English messages with a correlation ID, logs details server-side without sensitive data, and avoids user enumeration in login and password recovery.
---

# T159: Follow best practices for secure error and exception handling

**Category:** CODE_FIX
**SD Elements:** [T159](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T159/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: filters, loading states and error messages. Adapt navigation to the user profiles)
> Source: specs/PRD.md, line 13

> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
To show "error messages", developers often forward `str(exc)` (Postgres/PostgREST errors, Supabase messages, stack traces) to the UI, and display "user not found" vs "wrong password" on login. This leaks schema details and enables user enumeration.

**Secure Implementation Pattern:**
```python
# backend/app/core/errors.py
import logging, uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("acme.app")

MESSAGES = {  # centralized, user-facing (English per PRD)
    "auth_failed": "Invalid email or password.",
    "reset_sent": "If an account exists for this email, a reset link has been sent.",
    "forbidden": "You do not have permission to perform this action.",
    "not_found": "The requested resource was not found.",
    "internal": "Something went wrong. Please try again or contact support.",
}

class AppError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status

def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse({"error": exc.code, "message": MESSAGES[exc.code]}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = {403: "forbidden", 404: "not_found"}.get(exc.status_code, "internal")
        return JSONResponse({"error": code, "message": MESSAGES[code]}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex
        log.exception("unhandled_error", extra={"error_id": error_id, "path": request.url.path})
        return JSONResponse({"error": "internal", "message": MESSAGES["internal"],
                             "error_id": error_id}, status_code=500)
```

**Implementation Guidance:**
- Implement in `backend/app/core/errors.py`; call `install_error_handlers(app)` in `main.py`. Also override the `RequestValidationError` handler to return field names only, not echoed input.
- Never return `str(exc)` from Supabase/PostgREST/psycopg errors; map known cases to catalogue codes. Check return values from Supabase calls (`.data`, `.error`, Storage upload responses) instead of ignoring them.
- Login and password recovery: same message for unknown e-mail and wrong password; recovery always returns `reset_sent`.
- Log full details (with `error_id`) server-side via `acme.app`, without PHI or tokens (T46).
- Frontend (`frontend/src/services`, `components`): show catalogue messages plus the `error_id`; never render raw response bodies.
- Disable FastAPI debug (`FastAPI(debug=False)`) and default docs in production (T105).
- Reference: SD Elements guidance for T159.

**Success Criteria:**
- [ ] All error responses match `{error, message[, error_id]}` from the catalogue.
- [ ] Pytest: a forced exception returns 500 with generic text and no traceback/SQL.
- [ ] Pytest: login with unknown e-mail and wrong password return identical bodies.

**Status:** Applied
