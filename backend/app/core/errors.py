"""Global exception handlers returning minimal, generic error messages.

Internal details (stack traces, SQL, library messages) are logged server-side with a request id
and never returned to the client.
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

log = logging.getLogger("acme.errors")


class DomainError(Exception):
    """Expected business-rule violation with a safe, user-facing message."""

    def __init__(self, message: str, status_code: int = status.HTTP_409_CONFLICT):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"error": exc.detail, "request_id": _rid(request)}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Return field locations and messages only; never echo submitted values back.
        fields = [{"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg", "Invalid value")}
                  for e in exc.errors()[:20]]
        return JSONResponse({"error": "Invalid request.", "fields": fields, "request_id": _rid(request)},
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"error": exc.message, "request_id": _rid(request)}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", extra={"request_id": _rid(request), "path": request.url.path,
                                            "error_type": type(exc).__name__}, exc_info=exc)
        return JSONResponse({"error": "An unexpected error occurred. Please try again.", "request_id": _rid(request)},
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
