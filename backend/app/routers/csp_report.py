"""API router: Content-Security-Policy violation reports from the SPA (T1469).

Browsers post reports without credentials, so this is the only public POST route (whitelisted in
``PUBLIC_ROUTES``). Defences:

* Accepted media types: ``application/csp-report`` (report-uri), ``application/reports+json``
  (Reporting API, a JSON array) and ``application/json``; anything else is ignored.
* Body limited to ``MAX_REPORT_BYTES`` (8 KiB) on top of the global body-size middleware.
* Only allow-listed fields are logged, as bounded strings; URLs are reduced to their origin so
  paths/query strings (which could contain identifiers) never reach the logs.
* Always answers 204 with no body (no oracle, nothing reflected), and is rate-limited per IP by
  ``RateLimitMiddleware`` (route rule ``csp-report``).
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/v1", tags=["csp"])
log = logging.getLogger("acme.security.csp")

MAX_REPORT_BYTES = 8 * 1024
MAX_REPORTS = 10
ACCEPTED_TYPES = frozenset({"application/csp-report", "application/reports+json", "application/json"})
# report-uri (kebab-case) and Reporting API (camelCase) names -> log field
_FIELDS = {
    "document-uri": "document", "documentURL": "document",
    "blocked-uri": "blocked", "blockedURL": "blocked",
    "referrer": "referrer",
    "violated-directive": "directive", "effective-directive": "directive", "effectiveDirective": "directive",
    "disposition": "disposition",
    "status-code": "status", "statusCode": "status",
}
_URL_FIELDS = frozenset({"document", "blocked", "referrer"})
_TOKEN = re.compile(r"[^A-Za-z0-9 :._'-]")


def origin_only(value: object) -> str:
    """Reduce a URL to scheme://host[:port]; keywords such as 'inline' / 'eval' are kept as bounded tokens."""
    text = str(value)[:2048]
    parts = urlsplit(text)
    if parts.scheme in ("http", "https", "wss", "ws") and parts.hostname:
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{parts.hostname}{port}"[:200]
    return _TOKEN.sub("", text.split(":", 1)[0] if parts.scheme else text)[:40]


def sanitize_report(report: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, field in _FIELDS.items():
        if key in report and field not in out and report[key] is not None:
            value = report[key]
            out[field] = origin_only(value) if field in _URL_FIELDS else _TOKEN.sub("", str(value))[:80]
    return out


def _reports(payload: object) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("csp-report"), dict):
        return [payload["csp-report"]]
    if isinstance(payload, list):  # Reporting API: [{"type": "csp-violation", "body": {...}}, ...]
        return [r["body"] for r in payload[:MAX_REPORTS]
                if isinstance(r, dict) and r.get("type") == "csp-violation" and isinstance(r.get("body"), dict)]
    return []


@router.post("/csp-report", status_code=204, include_in_schema=False)
async def csp_report(request: Request) -> Response:
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type in ACCEPTED_TYPES:
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_REPORT_BYTES:
                body = b""
                break
        try:
            payload = json.loads(body) if body else None
        except (ValueError, UnicodeDecodeError):
            payload = None
        for report in _reports(payload):
            fields = sanitize_report(report)
            if fields:
                log.warning("csp_violation", extra={"csp": fields, "request_id": getattr(request.state, "request_id", None)})
    return Response(status_code=204)
