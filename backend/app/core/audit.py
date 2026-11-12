"""Audit trail for clinical and security-relevant actions.

Events are written to the append-only, hash-chained `public.events` table (see 0001_schema.sql)
and mirrored as structured security log lines. Details must never contain free-text clinical
content, passwords or tokens: callers pass identifiers and enumerated values only.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from psycopg import AsyncConnection

from app.core.logging import redact, security_log

log = logging.getLogger("acme.audit")


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
) -> None:
    safe_details = redact(details or {})
    security_log.info(action, extra={"outcome": outcome, "entity_type": entity_type, "entity_id": entity_id,
                                     "actor_id": str(principal.user_id) if principal else None,
                                     "actor_role": principal.role.value if principal else None,
                                     "request_id": request_id, "details": safe_details})
    sql = ("insert into public.events (actor_id, actor_role, action, entity_type, entity_id, outcome, request_id, details)"
           " values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)")
    params = (str(principal.user_id) if principal else None, principal.role.value if principal else None,
              action, entity_type, entity_id, outcome, request_id, json.dumps(safe_details))
    try:
        if conn is not None:
            await conn.execute(sql, params)
        else:
            from app.db import transaction

            async with transaction(principal) as c:
                await c.execute(sql, params)
    except Exception:  # audit-store failure must be visible but must not leak details to the client
        log.error("audit_write_failed", extra={"action": action, "entity_type": entity_type})
        if conn is not None:
            raise  # inside a business transaction: fail closed so the action is not committed unaudited
