"""Global exception handlers returning minimal, generic, catalogued error messages (T159/T403).

* Every error body is `{"error": <user-facing message>, "code": <catalogue code>, "request_id": <id>}`
  (plus `fields` for validation errors). `request_id` doubles as the error id users can quote.
* Internal details (stack traces, SQL, library messages) are logged server-side with the request
  id and never returned to the client.
* Database unavailability / lock timeouts fail to a known state: HTTP 503 with an explicit code
  (`monitoring_unavailable`, `busy`) and `Retry-After`, so the UI shows "Monitoring unavailable"
  instead of an empty, normal-looking screen (T347/T433).
* Security-relevant failures (401, 403, 404, 405, 422, 5xx) are emitted as `acme.security` events (T45).

`install_error_handlers` also installs the request-context middleware (source IP / request id
for logs and audit records) and the priority / load-shedding middleware (T363), because the
error handlers depend on both.
"""

from __future__ import annotations

import logging
import ssl

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors
from psycopg import OperationalError
from psycopg_pool import PoolTimeout
from starlette import status
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import RequestContextMiddleware, sec_event

log = logging.getLogger("acme.errors")

MESSAGES: dict[str, str] = {
    "auth_required": "Authentication required.",
    "forbidden": "You do not have permission to perform this action.",
    "not_found": "The requested resource was not found.",
    "method_not_allowed": "Method not allowed.",
    "invalid_request": "Invalid request.",
    "conflict": "The request conflicts with the current state. Reload and try again.",
    "monitoring_unavailable": "Live monitoring data is temporarily unavailable. Check patients directly at the bedside.",
    "busy": "The system is busy. Please try again in a moment.",
    "internal": "An unexpected error occurred. Please try again.",
}
_STATUS_CODES = {401: "auth_required", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
                 409: "conflict", 413: "too_large", 415: "unsupported_media_type", 422: "invalid_request",
                 429: "rate_limited", 503: "busy"}
_SECURITY_EVENTS = {401: "authn_failed", 403: "authz_denied", 404: "resource_not_found", 405: "method_not_allowed"}


class DomainError(Exception):
    """Expected business-rule violation with a safe, user-facing message."""

    def __init__(self, message: str, status_code: int = status.HTTP_409_CONFLICT, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code or _STATUS_CODES.get(status_code, "error")


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def error_body(request: Request, message: str, code: str, **extra: object) -> dict:
    return {"error": message, "code": code, "request_id": _rid(request), **extra}


def is_tls_verification_failure(exc: BaseException) -> bool:
    """True when an exception (or its cause chain) is a TLS certificate / hostname verification failure."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(current):
            return True
        current = current.__cause__ or current.__context__
    return False


def install_error_handlers(app: FastAPI) -> None:
    from app.services.resilience import PriorityMiddleware, note_db_failure

    app.add_middleware(PriorityMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        if exc.status_code in _SECURITY_EVENTS:
            sec_event(_SECURITY_EVENTS[exc.status_code], outcome="denied" if exc.status_code in (401, 403) else "failure",
                      status=exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) and exc.status_code < 500 else MESSAGES.get(code, MESSAGES["internal"])
        if exc.status_code == 404 and message == "Not Found":
            message = MESSAGES["not_found"]
        if exc.status_code == 405:
            message = MESSAGES["method_not_allowed"]
        headers = getattr(exc, "headers", None)
        if exc.status_code == 401 and headers and "step_up_required" in headers.get("WWW-Authenticate", ""):
            code = "step_up_required"  # the SPA re-authenticates and retries instead of signing out
        return JSONResponse(error_body(request, message, code), status_code=exc.status_code, headers=headers)


    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Return field locations and messages only; never echo submitted values back.
        fields = [{"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": str(e.get("msg", "Invalid value"))[:200]}
                  for e in exc.errors()[:20]]
        sec_event("input_validation_failed", outcome="failure", fields=",".join(f["field"] for f in fields))
        return JSONResponse(error_body(request, MESSAGES["invalid_request"], "invalid_request", fields=fields),
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers = {"Retry-After": "15"} if exc.status_code == 503 else None
        return JSONResponse(error_body(request, exc.message, exc.code), status_code=exc.status_code, headers=headers)

    async def unavailable(request: Request, exc: Exception) -> JSONResponse:
        note_db_failure()
        log.error("database_unavailable", extra={"request_id": _rid(request), "path": request.url.path,
                                                 "error_type": type(exc).__name__})
        sec_event("dependency_unavailable", outcome="failure", level=logging.ERROR, error_type=type(exc).__name__)
        return JSONResponse(error_body(request, MESSAGES["monitoring_unavailable"], "monitoring_unavailable", degraded=True),
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, headers={"Retry-After": "15"})

    async def busy(request: Request, exc: Exception) -> JSONResponse:
        log.warning("lock_contention", extra={"request_id": _rid(request), "error_type": type(exc).__name__})
        return JSONResponse(error_body(request, MESSAGES["busy"], "busy"), status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            headers={"Retry-After": "5"})

    async def duplicate(request: Request, exc: Exception) -> JSONResponse:
        # A unique constraint (one active patient per identity, one monitor per bed, ...) refused a duplicate
        # record (T742): a known 409, never a 500 with the constraint text.
        log.info("unique_violation", extra={"request_id": _rid(request), "path": request.url.path})
        return JSONResponse(error_body(request, MESSAGES["conflict"], "conflict"), status_code=status.HTTP_409_CONFLICT)

    async def upstream_unavailable(request: Request, exc: Exception) -> JSONResponse:
        # Outbound call to Supabase failed. A certificate / chain / hostname failure is a security event; the
        # client never falls back to plaintext or unverified TLS and gets a generic 503 (T156/T21).
        tls = is_tls_verification_failure(exc)
        sec_event("tls_verification_failed" if tls else "dependency_unavailable", outcome="failure",
                  level=logging.ERROR, error_type=type(exc).__name__, dependency="supabase")
        return JSONResponse(error_body(request, MESSAGES["busy"], "dependency_unavailable"),
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, headers={"Retry-After": "15"})

    app.add_exception_handler(pg_errors.UniqueViolation, duplicate)
    app.add_exception_handler(httpx.TransportError, upstream_unavailable)
    for exc_type in (OperationalError, PoolTimeout):
        app.add_exception_handler(exc_type, unavailable)
    for exc_type in (pg_errors.LockNotAvailable, pg_errors.DeadlockDetected, pg_errors.QueryCanceled):
        app.add_exception_handler(exc_type, busy)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", extra={"request_id": _rid(request), "path": request.url.path,
                                            "error_type": type(exc).__name__}, exc_info=exc)
        sec_event("unhandled_error", outcome="failure", level=logging.ERROR, error_type=type(exc).__name__)
        return JSONResponse(error_body(request, MESSAGES["internal"], "internal"),
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
