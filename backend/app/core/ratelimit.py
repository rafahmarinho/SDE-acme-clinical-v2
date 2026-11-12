"""Shared, per-user throttling for expensive operations (T1362).

``RateLimitMiddleware`` (app/core/middleware.py) keeps in-memory token buckets, which only bound one
Vercel instance and key on a token hash. Expensive routes additionally call ``enforce_shared_limit`` inside
their transaction: ``public.consume_rate_limit`` (supabase/migrations/0009_rate_limits.sql) counts requests
per VERIFIED user id (``app.user_id``) and one-minute window in PostgreSQL, so the budget holds across
instances and across token rotation. Budgets are the same per-minute values as the middleware route rules.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException

from app.core.middleware import ROUTE_LIMITS

log = logging.getLogger("acme.security")

SHARED_LIMIT_SQL = "select public.consume_rate_limit(%s, %s) as retry_after"
SHARED_LIMITS: dict[str, int] = {rule.name: rule.per_minute for rule in ROUTE_LIMITS if rule.name != "csp-report"}

FetchOne = Callable[[Any, str, Any], Awaitable[dict | None]]


async def enforce_shared_limit(conn: Any, name: str, fetch_one: FetchOne) -> None:
    """Consume one request of the ``name`` budget for the transaction's caller; raise 429 when exhausted.

    ``fetch_one`` is the calling module's DB helper (``app.db.fetch_one``), passed in so the query runs on the
    caller's connection and transaction.
    """
    per_minute = SHARED_LIMITS[name]  # KeyError for an unknown budget: a programming error, never request data
    row = await fetch_one(conn, SHARED_LIMIT_SQL, (name, per_minute))
    retry_after = row.get("retry_after") if isinstance(row, dict) else None
    if isinstance(retry_after, int) and not isinstance(retry_after, bool) and retry_after > 0:
        log.warning("rate_limited", extra={"budget": name, "scope": "shared"})
        raise HTTPException(429, "Too many requests. Please slow down.", headers={"Retry-After": str(retry_after)})
