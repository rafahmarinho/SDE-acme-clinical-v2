"""Structured application and security logging. No confidential data in logs.

* Logs are JSON lines on stdout (collected by Vercel log drains) with UTC ISO-8601 timestamps
  in milliseconds. A redaction layer masks tokens, passwords, secrets, e-mails, signed URLs and
  free-text clinical content (T46); log entries are length-capped.
* `acme.security` is a separate logger for security events (T45). `sec_event` adds the request
  context (request id, source IP, method, path, user id) captured by `RequestContextMiddleware`.
* `FAILURE_POLICY` is the catalogue of minor failures and the designed response to each (T431).
  If logging itself fails, the failure is counted and the request continues.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

SENSITIVE_KEYS = re.compile(
    r"(pass(word)?|secret|token|authorization|cookie|api[_-]?key|jwt|body|note|email|signed_?url|"
    r"display_name|full_name|patient_name|reason|ecg)", re.I)
BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+")
JWT_LIKE = re.compile(r"eyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
KEY_VALUE = re.compile(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\b(\"?\s*[:=]\s*\"?)[^\s\",}&]+")
MAX_ENTRY_CHARS = 2000
MAX_FIELD_CHARS = 200

_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


def _redact_str(value: str) -> str:
    value = BEARER.sub("Bearer [REDACTED]", value)
    value = JWT_LIKE.sub("[REDACTED_JWT]", value)
    value = KEY_VALUE.sub(r"\1\2[REDACTED]", value)
    return EMAIL.sub("[REDACTED_EMAIL]", value)


def redact(value: object) -> object:
    """Mask confidential content. Under sensitive keys, text/structures are removed entirely;
    booleans and numbers (e.g. `has_note`, `password_min_length`) carry no content and are kept."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if SENSITIVE_KEYS.search(str(k)) and not isinstance(v, (bool, int, float, type(None))):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _redact_str(value)
    return value


def utc_now_ms() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


# ---------------------------------------------------------------------------
# Request context (source IP, request id, path) for security events and audit records
# ---------------------------------------------------------------------------
@dataclass
class RequestContext:
    request_id: str | None = None
    source_ip: str | None = None
    method: str | None = None
    path: str | None = None
    state: dict = field(default_factory=dict)

    @property
    def user_id(self) -> str | None:
        principal = self.state.get("principal")
        return str(principal.user_id) if principal is not None else None


_ctx: ContextVar[RequestContext | None] = ContextVar("acme_request_ctx", default=None)


def current_context() -> RequestContext:
    ctx = _ctx.get()
    if ctx is None:
        return RequestContext()
    ctx.request_id = ctx.request_id or ctx.state.get("request_id")
    return ctx


def client_ip(headers: dict[bytes, bytes], peer: str | None) -> str | None:
    """Vercel sets x-vercel-forwarded-for / x-real-ip at the edge; fall back to the socket peer."""
    for name in (b"x-vercel-forwarded-for", b"x-real-ip"):
        raw = headers.get(name)
        if raw:
            peer = raw.decode("latin-1").split(",")[0].strip()
            break
    try:
        return str(ipaddress.ip_address(peer)) if peer else None
    except ValueError:
        return None


class RequestContextMiddleware:
    """Pure ASGI middleware that exposes the request context to logging and auditing."""

    def __init__(self, app):  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        state = scope.setdefault("state", {})
        peer = scope.get("client")[0] if scope.get("client") else None
        ctx = RequestContext(request_id=state.get("request_id"), source_ip=client_ip(dict(scope.get("headers") or []), peer),
                             method=scope.get("method"), path=scope.get("path"), state=state)
        token = _ctx.set(ctx)
        try:
            return await self.app(scope, receive, send)
        finally:
            _ctx.reset(token)


# ---------------------------------------------------------------------------
# Failure catalogue (T431) - source list for the T432 tests
# ---------------------------------------------------------------------------
class FailureAction(StrEnum):
    BUFFER_AND_RETRY = "buffer_and_retry"            # keep the event in memory, retry on next write, alert admins
    DROP_OLDEST_AND_ALERT = "drop_oldest_and_alert"  # bounded buffer: oldest buffered event dropped, critical alert
    BLOCK_ACTION = "block_action"                    # action needing non-repudiation is refused (503), rolled back
    COUNT_AND_CONTINUE = "count_and_continue"        # log sink error: count, never raise into request handling
    FALLBACK_TO_STDOUT = "fallback_to_stdout"        # admin alert row cannot be stored: critical stdout line only


FAILURE_POLICY: dict[str, FailureAction] = {
    "audit_insert_failed": FailureAction.BUFFER_AND_RETRY,
    "audit_buffer_full": FailureAction.DROP_OLDEST_AND_ALERT,
    "critical_audit_failed": FailureAction.BLOCK_ACTION,
    "audit_signing_failed": FailureAction.BLOCK_ACTION,
    "log_sink_error": FailureAction.COUNT_AND_CONTINUE,
    "alert_store_failed": FailureAction.FALLBACK_TO_STDOUT,
}

failure_counters: dict[str, int] = {key: 0 for key in FAILURE_POLICY}


def count_failure(key: str) -> None:
    failure_counters[key] = failure_counters.get(key, 0) + 1


# ---------------------------------------------------------------------------
# Formatting / handlers
# ---------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": redact(record.getMessage()),
        }
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD}
        payload.update(redact(extras))  # type: ignore[arg-type]
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        line = json.dumps(payload, default=str)
        return line if len(line) <= MAX_ENTRY_CHARS else json.dumps(
            {k: payload[k] for k in ("ts", "level", "logger", "event")} | {"truncated": True}, default=str)[:MAX_ENTRY_CHARS]


class RedactingFilter(logging.Filter):
    """Defence in depth for any handler/formatter: rewrite the message itself, capped in length."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # malformed format args must not break logging
            msg = str(record.msg)
        record.msg, record.args = _redact_str(msg)[:MAX_ENTRY_CHARS], ()
        return True


class SafeStreamHandler(logging.StreamHandler):
    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802 - stdlib name
        count_failure("log_sink_error")  # degrade gracefully; never raise into request handling


def configure_logging(production: bool) -> None:
    handler = SafeStreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO if production else logging.DEBUG)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs may contain signed tokens
    security_log.info("logging_initialised", extra={"outcome": "success", "production": production})


security_log = logging.getLogger("acme.security")


def sec_event(event: str, *, outcome: str, level: int = logging.INFO, **fields: Any) -> None:
    """Emit one security event on `acme.security` with ts, event, outcome, user_id, ip (T45)."""
    ctx = current_context()
    entry: dict[str, Any] = {"outcome": outcome, "user_id": ctx.user_id, "ip": ctx.source_ip,
                             "request_id": ctx.request_id, "method": ctx.method, "path": ctx.path,
                             "event_ts": utc_now_ms()}
    for key, value in fields.items():
        entry[key] = value if isinstance(value, (bool, int, float, type(None))) else str(value)[:MAX_FIELD_CHARS]
    try:
        security_log.log(level, event, extra=entry)
    except Exception:
        count_failure("log_sink_error")
