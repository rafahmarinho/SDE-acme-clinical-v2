"""HTTP hardening middleware: request ids, security headers, body-size limits, method allow-list
and per-client rate limiting.

Rate limiting here is a per-instance token bucket (Vercel functions are short-lived and scaled
horizontally), so it is a defence-in-depth layer; Vercel Firewall rate limits are the primary control.
"""

from __future__ import annotations

import re
import secrets
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    # Every API response may contain patient or staff data.
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request.state.request_id = incoming if _REQUEST_ID.match(incoming) else secrets.token_hex(12)
        if request.method not in ALLOWED_METHODS:
            response: Response = JSONResponse({"error": "Method not allowed."}, status_code=405)
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        response.headers["X-Request-Id"] = request.state.request_id
        for leaky in ("server", "x-powered-by"):
            if leaky in response.headers:
                del response.headers[leaky]
        return response


class BodySizeLimitMiddleware:
    """Reject request bodies larger than the configured limit (checks header and streamed size)."""

    def __init__(self, app: ASGIApp, max_bytes: int, upload_max_bytes: int, upload_prefix: str = "/v1/files"):
        self.app, self.max_bytes, self.upload_max, self.upload_prefix = app, max_bytes, upload_max_bytes, upload_prefix

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self.upload_max if scope["path"].startswith(self.upload_prefix) else self.max_bytes
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            return await JSONResponse({"error": "Request too large."}, status_code=413)(scope, receive, send)

        received = 0

        async def limited_receive():  # type: ignore[no-untyped-def]
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        try:
            return await self.app(scope, limited_receive, send)
        except _TooLarge:
            return await JSONResponse({"error": "Request too large."}, status_code=413)(scope, receive, send)


class _TooLarge(Exception):
    pass


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, per_minute: int, auth_per_minute: int):
        super().__init__(app)
        self.per_minute, self.auth_per_minute = per_minute, auth_per_minute
        self._buckets: dict[str, tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))

    def _key(self, request: Request) -> str:
        # Prefer the authenticated subject if a token is present, else the client address set by Vercel.
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer ") and len(auth) > 20:
            return "t:" + auth[-24:]
        forwarded = request.headers.get("x-vercel-forwarded-for") or (request.client.host if request.client else "?")
        return "ip:" + forwarded.split(",")[0].strip()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        sensitive = request.url.path.startswith(("/v1/auth", "/v1/break-glass"))
        limit = self.auth_per_minute if sensitive else self.per_minute
        key = ("auth|" if sensitive else "") + self._key(request)
        now = time.monotonic()
        tokens, last = self._buckets[key]
        tokens = min(float(limit), tokens + (now - last) * (limit / 60.0)) if last else float(limit)
        if tokens < 1:
            return JSONResponse({"error": "Too many requests. Please slow down."}, status_code=429,
                                headers={"Retry-After": "60"})
        self._buckets[key] = (tokens - 1, now)
        if len(self._buckets) > 10_000:  # bound memory
            self._buckets.clear()
        return await call_next(request)
