"""Structured application and security logging. No confidential data in logs.

Logs are JSON lines on stdout (collected by Vercel log drains). A redaction filter masks
tokens, passwords, secrets, emails and free-text clinical content before anything is emitted.
If logging itself fails, the failure is swallowed and counted so the request is not lost.
"""

import json
import logging
import re
import sys
from datetime import UTC, datetime

SENSITIVE_KEYS = re.compile(r"(pass(word)?|secret|token|authorization|cookie|api[_-]?key|jwt|body|note|email)", re.I)
BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._-]+")
JWT_LIKE = re.compile(r"eyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}
logging_failures = 0


def redact(value: object) -> object:
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if SENSITIVE_KEYS.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = BEARER.sub("Bearer [REDACTED]", value)
        value = JWT_LIKE.sub("[REDACTED_JWT]", value)
        return EMAIL.sub("[REDACTED_EMAIL]", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": redact(record.getMessage()),
        }
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD}
        payload.update(redact(extras))  # type: ignore[arg-type]
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str)


class SafeStreamHandler(logging.StreamHandler):
    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802 - stdlib name
        global logging_failures
        logging_failures += 1  # degrade gracefully; never raise into request handling


def configure_logging(production: bool) -> None:
    handler = SafeStreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO if production else logging.DEBUG)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


security_log = logging.getLogger("acme.security")
