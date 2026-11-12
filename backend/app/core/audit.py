"""Audit trail for clinical and security-relevant actions.

Each record captures who (actor id/role, session id, AAL), from where (source IP), what
(action, entity, enumerated details), when (DB clock + signed UTC ms timestamp), the outcome and
an error code for failures (T71). Records are:

* written to the append-only, hash-chained `public.events` table (0001/0004 migrations);
* signed with ECDSA P-521/SHA-512 over a canonical payload (non-repudiation, T485), verifiable
  through `GET /v1/events/integrity` and the published key `GET /v1/events/signing-key`;
* mirrored as structured `acme.security` log lines.

Details must never contain free-text clinical content, passwords or tokens: callers pass
identifiers and enumerated values only (and `redact` enforces it, T46).

Failure handling (T431, see FAILURE_POLICY in core/logging.py):
* inside a business transaction, actions in CRITICAL scope (anything not listed in MINOR_ACTIONS)
  are refused with HTTP 503 and rolled back when their audit record cannot be written;
* minor events (reads, simulation ticks, denials) never block the request: they are buffered in
  memory (bounded), retried on the next successful write, and administrators are alerted.
"""

from __future__ import annotations

import collections
import json
import logging
import time
from types import SimpleNamespace
from typing import Any

from psycopg import AsyncConnection
from starlette import status

from app.core.errors import DomainError
from app.core.logging import count_failure, current_context, redact, sec_event, security_log, utc_now_ms

log = logging.getLogger("acme.audit")

RECORD_VERSION = 1
MAX_DETAILS_BYTES = 3500  # DB check is 4096 bytes on the jsonb column

# Events whose loss must not block the user's action (alarm generation, reads, denials).
MINOR_ACTIONS = frozenset({
    "simulation.advanced", "report.generated", "report.exported", "file.accessed", "patient.viewed",
    "authz.denied", "auth.login", "auth.logout", "events.verified", "watchdog.connection_lost", "alarm.ack_rejected",
    "file.rejected", "alert.acknowledged",
})

BUFFER_MAX = 500
_buffer: collections.deque[tuple[Any, str, tuple]] = collections.deque(maxlen=BUFFER_MAX)
_last_alert: dict[str, float] = {}
ALERT_MIN_INTERVAL_SECONDS = 60
# The only keys an administrator alert may carry: identifiers and counters, never personal or clinical content.
ALERT_DETAIL_KEYS = frozenset({"action", "activity", "attachment_id", "client_ip", "entity_id", "monitor_id",
                               "patient_id", "per_minute", "status", "user_id"})

INSERT_SQL = (
    "insert into public.events (actor_id, actor_role, action, entity_type, entity_id, outcome, request_id, details,"
    " source_ip, session_id, aal, error_code, signed_at, key_id, signature)"
    " values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)"
)


class AuditUnavailable(DomainError):
    def __init__(self) -> None:
        super().__init__("This action could not be recorded in the audit trail, so it was not saved. Please try again.",
                         status.HTTP_503_SERVICE_UNAVAILABLE, code="audit_unavailable")


def is_critical(action: str) -> bool:
    return action not in MINOR_ACTIONS


def _cap_details(details: dict[str, Any]) -> dict[str, Any]:
    safe = redact(details or {})
    assert isinstance(safe, dict)
    for key, value in list(safe.items()):
        if isinstance(value, str) and len(value) > 200:
            safe[key] = value[:200]
    if len(json.dumps(safe, default=str)) > MAX_DETAILS_BYTES:
        return {"truncated": True, "keys": sorted(safe)[:20]}
    return json.loads(json.dumps(safe, default=str))


def signed_payload(row: dict[str, Any]) -> dict[str, Any]:
    """The exact fields covered by the signature (reconstructible from a stored events row)."""
    return {
        "v": RECORD_VERSION, "key_id": row.get("key_id"), "signed_at": row.get("signed_at"),
        "actor_id": row.get("actor_id"), "actor_role": row.get("actor_role"), "session_id": row.get("session_id"),
        "aal": row.get("aal"), "source_ip": row.get("source_ip"), "action": row.get("action"),
        "entity_type": row.get("entity_type"), "entity_id": row.get("entity_id"), "outcome": row.get("outcome"),
        "error_code": row.get("error_code"), "request_id": row.get("request_id"), "details": row.get("details") or {},
    }


def verify_row(row: dict[str, Any]) -> bool:
    """True when a stored events row carries a valid signature over its own fields."""
    from app.services import integrity

    if not row.get("signature") or row.get("key_id") != integrity.key_id():
        return False
    normalized = {**row, "actor_id": str(row["actor_id"]) if row.get("actor_id") else None,
                  "actor_role": str(row["actor_role"]) if row.get("actor_role") else None}
    return integrity.verify(signed_payload(normalized), row["signature"])


def build_record(principal: Any | None, action: str, entity_type: str, entity_id: str | None, *, outcome: str,
                 details: dict[str, Any] | None, request_id: str | None, error_code: str | None) -> dict[str, Any]:
    from app.services import integrity

    ctx = current_context()
    record = {
        "actor_id": str(principal.user_id) if principal else None,
        "actor_role": principal.role.value if principal else None,
        "session_id": (str(getattr(principal, "session_id", "") or "")[:64] or None) if principal else None,
        "aal": getattr(principal, "aal", None) if principal else None,
        "source_ip": ctx.source_ip,
        "action": action, "entity_type": entity_type, "entity_id": entity_id, "outcome": outcome,
        "error_code": error_code, "request_id": request_id or ctx.request_id,
        "details": _cap_details(details or {}), "signed_at": utc_now_ms(), "key_id": integrity.key_id(),
    }
    record["signature"] = integrity.sign(signed_payload(record))
    return record


def _params(r: dict[str, Any]) -> tuple:
    return (r["actor_id"], r["actor_role"], r["action"], r["entity_type"], r["entity_id"], r["outcome"], r["request_id"],
            json.dumps(r["details"]), r["source_ip"], r["session_id"], r["aal"], r["error_code"], r["signed_at"],
            r["key_id"], r["signature"])


def alert_details(details: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only allow-listed identifier keys in an admin alert (T1386): alerts may be forwarded to e-mail or
    chat later, so patient names, MRNs, vitals or free text never travel in them - only ids and a link."""
    return {k: v for k, v in (details or {}).items() if k in ALERT_DETAIL_KEYS}


async def notify_admins(kind: str, details: dict[str, Any] | None = None) -> None:
    """Alert administrators: critical security log line (log-drain alerting) plus a `system_alerts` row
    (shown on the admin events screen). Rate-limited per kind; never raises."""
    now = time.monotonic()
    details = alert_details(details)
    security_log.critical("admin_alert", extra={"alert": kind, "details": redact(details)})
    if now - _last_alert.get(kind, -1e9) < ALERT_MIN_INTERVAL_SECONDS:
        return
    _last_alert[kind] = now
    try:
        from app.db import transaction

        async with transaction(None) as c:
            await c.execute("insert into public.system_alerts (kind, severity, details) values (%s, %s, %s::jsonb)",
                            (kind[:40], "critical" if kind in ("critical_audit_failed", "audit_buffer_full") else "warning",
                             json.dumps(_cap_details(details or {}))))
    except Exception:
        count_failure("alert_store_failed")
        log.critical("alert_store_failed", extra={"alert": kind})


def _buffer_event(principal: Any | None, record: dict[str, Any]) -> bool:
    """Returns True when the buffer was already full (oldest buffered event dropped)."""
    full = len(_buffer) == _buffer.maxlen
    if full:
        count_failure("audit_buffer_full")
    stand_in = SimpleNamespace(user_id=principal.user_id, role=principal.role) if principal else None
    _buffer.append((stand_in, record["action"], _params(record)))
    return full


async def flush_buffer(max_items: int = 50) -> int:
    """Retry buffered events, each in its own transaction under its original actor (RLS)."""
    from app.db import transaction

    flushed = 0
    while _buffer and flushed < max_items:
        stand_in, _action, params = _buffer[0]
        try:
            async with transaction(stand_in) as c:
                await c.execute(INSERT_SQL, params)
        except Exception:
            return flushed
        _buffer.popleft()
        flushed += 1
    return flushed


async def record_event(
    principal: Any | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    *,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
    conn: AsyncConnection | None = None,
    request_id: str | None = None,
    error_code: str | None = None,
) -> None:
    critical = conn is not None and is_critical(action)
    try:
        record = build_record(principal, action, entity_type, entity_id, outcome=outcome, details=details,
                              request_id=request_id, error_code=error_code)
    except Exception as exc:
        count_failure("audit_signing_failed")
        log.error("audit_signing_failed", extra={"action": action, "error_type": type(exc).__name__})
        await notify_admins("audit_signing_failed", {"action": action})
        if critical:
            raise AuditUnavailable() from exc
        return

    sec_event(action, outcome=outcome, entity_type=entity_type, entity_id=entity_id, error_code=error_code,
              actor_role=record["actor_role"])
    try:
        if conn is not None:
            if critical:
                await conn.execute(INSERT_SQL, _params(record))
            else:
                async with conn.transaction():  # savepoint: a failed minor audit insert must not abort the action
                    await conn.execute(INSERT_SQL, _params(record))
        else:
            from app.db import transaction

            async with transaction(principal) as c:
                await c.execute(INSERT_SQL, _params(record))
    except Exception as exc:  # audit-store failure must be visible but must not leak details to the client
        if critical:
            count_failure("critical_audit_failed")
            log.error("audit_write_failed", extra={"action": action, "entity_type": entity_type, "policy": "block_action"})
            await notify_admins("critical_audit_failed", {"action": action})
            raise AuditUnavailable() from exc
        count_failure("audit_insert_failed")
        log.error("audit_write_failed", extra={"action": action, "entity_type": entity_type, "policy": "buffer_and_retry"})
        dropped = _buffer_event(principal, record)
        await notify_admins("audit_buffer_full" if dropped else "audit_insert_failed", {"action": action})
        return
    if _buffer and conn is None:
        await flush_buffer()
