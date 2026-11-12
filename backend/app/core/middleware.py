"""HTTP hardening middleware: request ids, security headers, request hygiene, body-size and JSON
structure limits, method allow-list and per-client / per-route rate limiting.

Order of execution (outermost first): SecurityHeadersMiddleware -> BodySizeLimitMiddleware ->
CORS -> RateLimitMiddleware -> routes. Malformed or oversized messages are therefore refused before
authentication, CORS or any route handler runs.

* ``SecurityHeadersMiddleware`` (T65, T74, T228, T599): method allow-list, method-override headers
  refused, Host allow-list, header count/size and URL length limits, duplicate single-valued query
  parameters refused (HTTP parameter pollution), security headers on every response, and a
  security log entry for every rejected request (T32).
* ``BodySizeLimitMiddleware`` (T34, T228, T537, T1148): declared and streamed (chunked) body size,
  JSON bodies must be ``application/json`` UTF-8, a single object, bounded depth, unique keys.
* ``RateLimitMiddleware`` (T1363): token buckets per client, per IP and per sensitive route.

Rate limiting here is a per-instance token bucket (Vercel functions are short-lived and scaled
horizontally), so it is a defence-in-depth layer; Vercel Firewall rate limits are the primary control.
"""

from __future__ import annotations

import logging
import math
import re
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass

import jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.validation import JsonStructureError, parse_json_object

security_log = logging.getLogger("acme.security")

ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
METHOD_OVERRIDE_HEADERS = ("x-http-method-override", "x-http-method", "x-method-override")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")

# HTTP message limits enforced by the application (Vercel's own ceilings are higher). See
# docs/security/input-validation.md for the full table.
MAX_HEADER_COUNT = 64
MAX_HEADER_BYTES = 16 * 1024
MAX_URL_BYTES = 2048
MAX_JSON_BODY_BYTES = 64 * 1024

# Query parameters that are explicitly modelled as typed, bounded ``list[...]`` and may repeat.
# Every other parameter is single-valued and a duplicate is refused (HTTP parameter pollution).
MULTI_VALUED_QUERY_PARAMS: frozenset[str] = frozenset()

# The API never builds links or makes access decisions from the Host header; this allow-list is a
# defence-in-depth guard against host-header poisoning. Override via the ``allowed_hosts`` argument.
DEFAULT_ALLOWED_HOSTS = ("*.vercel.app", "localhost", "127.0.0.1", "testserver")

REJECTION_STATUSES = frozenset({400, 405, 413, 414, 415, 422, 429, 431})

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


def client_ip(request: Request) -> str:
    """Client address as set by Vercel's edge (never the client-controlled X-Forwarded-For)."""
    forwarded = request.headers.get("x-vercel-forwarded-for") or request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "?"


def _error(message: str, status_code: int, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code, headers=headers)


def _host_allowed(host_header: str, allowed: Iterable[str]) -> bool:
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 literal
        host = host[1:host.find("]")] if "]" in host else ""
    else:
        host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    if not host:
        return False
    for pattern in allowed:
        pattern = pattern.lower()
        if pattern == "*" or host == pattern:
            return True
        if pattern.startswith("*.") and host.endswith(pattern[1:]) and host != pattern[2:]:
            return True
    return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str] | None = None):
        super().__init__(app)
        self.allowed_hosts = tuple(allowed_hosts) if allowed_hosts else DEFAULT_ALLOWED_HOSTS

    def _precheck(self, request: Request) -> JSONResponse | None:
        """Request hygiene checks that run before routing, CORS and authentication."""
        if request.method not in ALLOWED_METHODS:
            return _error("Method not allowed.", 405, {"Allow": ", ".join(sorted(ALLOWED_METHODS))})
        raw_headers = request.scope.get("headers") or []
        if len(raw_headers) > MAX_HEADER_COUNT or sum(len(k) + len(v) for k, v in raw_headers) > MAX_HEADER_BYTES:
            return _error("Request headers too large.", 431)
        if len(request.scope.get("raw_path") or request.url.path.encode()) + len(request.scope.get("query_string", b"")) > MAX_URL_BYTES:
            return _error("Request URL too long.", 414)
        if not _host_allowed(request.headers.get("host", ""), self.allowed_hosts):
            return _error("Invalid host.", 400)
        if any(h in request.headers for h in METHOD_OVERRIDE_HEADERS):
            return _error("HTTP method override is not supported.", 400)
        keys = [k for k, _ in request.query_params.multi_items()]
        if len(keys) != len(set(keys)) and any(keys.count(k) > 1 for k in set(keys) - MULTI_VALUED_QUERY_PARAMS):
            return _error("Duplicate query parameters are not allowed.", 400)
        return None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request.state.request_id = incoming if _REQUEST_ID.match(incoming) else secrets.token_hex(12)
        response: Response
        rejected = self._precheck(request)
        response = rejected if rejected is not None else await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        response.headers["X-Request-Id"] = request.state.request_id
        for leaky in ("server", "x-powered-by"):
            if leaky in response.headers:
                del response.headers[leaky]
        if response.status_code in REJECTION_STATUSES:
            # Security event for monitoring (AppSensor-style): route, status, source; never submitted values.
            security_log.warning("request_rejected", extra={
                "request_id": request.state.request_id, "method": request.method, "route": request.url.path,
                "status": response.status_code, "client_ip": client_ip(request),
                "code": "VALIDATION_422" if response.status_code == 422 else f"HTTP_{response.status_code}",
            })
        return response


class BodySizeLimitMiddleware:
    """Reject oversized bodies (declared and streamed/chunked) and structurally invalid JSON bodies."""

    def __init__(self, app: ASGIApp, max_bytes: int, upload_max_bytes: int, upload_prefix: str = "/v1/files",
                 json_max_bytes: int = MAX_JSON_BODY_BYTES):
        self.app, self.max_bytes, self.upload_max, self.upload_prefix = app, max_bytes, upload_max_bytes, upload_prefix
        self.json_max = min(max_bytes, json_max_bytes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        upload = scope["path"].startswith(self.upload_prefix)
        limit = self.upload_max if upload else self.json_max
        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            return await _error("Request too large.", 413)(scope, receive, send)
        if upload:
            return await self._streamed(scope, receive, send, limit)

        # JSON API: buffer the (small, bounded) body, validate its structure, then replay it.
        chunks: list[bytes] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            received += len(message.get("body", b""))
            if received > limit:
                return await _error("Request too large.", 413)(scope, receive, send)
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        if body.strip():
            content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
            media_type, _, params = content_type.partition(";")
            charset = params.strip().removeprefix("charset=").strip('"') if "charset=" in params else "utf-8"
            if media_type.strip() != "application/json" or charset not in ("utf-8", "utf8"):
                return await _error("Content-Type must be application/json.", 415)(scope, receive, send)
            try:
                parse_json_object(body)
            except JsonStructureError:
                return await _error("Malformed JSON request body.", 400)(scope, receive, send)

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)

    async def _streamed(self, scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        received = 0

        async def limited_receive() -> Message:
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
            return await _error("Request too large.", 413)(scope, receive, send)


class _TooLarge(Exception):
    pass


@dataclass(frozen=True)
class RouteLimit:
    """Extra per-route throttle for expensive or sensitive operations (requests per minute)."""

    name: str
    methods: frozenset[str]
    pattern: re.Pattern[str]
    per_minute: int


# Most specific first; the first matching rule applies (in addition to the per-client budget).
ROUTE_LIMITS: tuple[RouteLimit, ...] = (
    RouteLimit("simulation-reset", frozenset({"POST"}), re.compile(r"^/v1/simulation/reset/?$"), 3),
    RouteLimit("simulation", frozenset({"POST"}), re.compile(r"^/v1/simulation/"), 10),
    RouteLimit("reports", frozenset({"GET"}), re.compile(r"^/v1/reports/"), 5),
    RouteLimit("files-upload", frozenset({"POST"}), re.compile(r"^/v1/files/"), 10),
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token buckets: per client (verified-looking subject or IP), per IP ceiling, per sensitive route.

    * Sensitive authentication routes (``/v1/auth``, ``/v1/break-glass``) use ``auth_per_minute``.
    * ``ROUTE_LIMITS`` add stricter budgets for simulation, reports and uploads.
    * Requests without a bearer token are budgeted per IP at ``unauthenticated_per_minute``.
    * A per-IP ceiling (``ip_ceiling_factor`` x ``per_minute``) stops token-rotation bypasses.
    * The client IP comes from Vercel's edge header, never from a client-supplied X-Forwarded-For.
    """

    def __init__(self, app: ASGIApp, per_minute: int, auth_per_minute: int, unauthenticated_per_minute: int = 30,
                 ip_ceiling_factor: int = 5):
        super().__init__(app)
        self.per_minute, self.auth_per_minute = per_minute, auth_per_minute
        self.unauthenticated_per_minute = min(unauthenticated_per_minute, per_minute)
        self.ip_ceiling = per_minute * ip_ceiling_factor
        self._buckets: dict[str, tuple[float, float]] = {}

    @staticmethod
    def _subject(request: Request) -> str | None:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        try:  # bucketing only; the signature is verified by the auth dependency
            sub = jwt.decode(auth[7:].strip(), options={"verify_signature": False}).get("sub")
        except jwt.PyJWTError:
            return None
        return str(sub)[:64] if sub else None

    def _take(self, key: str, limit: int, now: float) -> float | None:
        """Consume one token; return None on success or the seconds until a token is available."""
        tokens, last = self._buckets.get(key, (float(limit), now))
        tokens = min(float(limit), tokens + (now - last) * (limit / 60.0))
        if tokens < 1:
            self._buckets[key] = (tokens, now)
            return (1 - tokens) * 60.0 / limit
        self._buckets[key] = (tokens - 1, now)
        return None

    def _budgets(self, request: Request) -> list[tuple[str, int]]:
        ip = client_ip(request)
        subject = self._subject(request)
        client = f"u:{subject}" if subject else f"ip:{ip}"
        path, method = request.url.path, request.method
        budgets = [(f"ceiling|ip:{ip}", self.ip_ceiling)]
        if path.startswith(("/v1/auth", "/v1/break-glass")):
            budgets.append((f"auth|{client}", self.auth_per_minute))
        budgets.append((f"all|{client}", self.per_minute if subject else self.unauthenticated_per_minute))
        for rule in ROUTE_LIMITS:
            if method in rule.methods and rule.pattern.match(path):
                budgets.append((f"{rule.name}|{client}", rule.per_minute))
                break
        return budgets

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        now = time.monotonic()
        for key, limit in self._budgets(request):
            wait = self._take(key, limit, now)
            if wait is not None:
                return _error("Too many requests. Please slow down.", 429, {"Retry-After": str(max(1, math.ceil(wait)))})
        if len(self._buckets) > 10_000:  # bound memory: drop buckets idle for over a minute
            self._buckets = {k: v for k, v in self._buckets.items() if now - v[1] < 60}
            if len(self._buckets) > 10_000:
                self._buckets.clear()
        return await call_next(request)
