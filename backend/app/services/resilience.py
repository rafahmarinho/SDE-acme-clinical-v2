"""Service priority scheme, degraded mode and bounded retries (T363, T433, T633).

Operation classes (highest priority first):

| Class            | Examples                                                         | Shed when      |
|------------------|------------------------------------------------------------------|----------------|
| EMERGENCY_SAFETY | alarm list/ack, monitor status, break-glass, auth/session, health | never          |
| MONITORING       | wards, patients + live readings, monitors, simulation advance     | shed level <= 1|
| MAIN_FUNCTION    | observations, thresholds, monitor binding, maintenance, files     | shed level <= 2|
| SUPERVISORY      | reports, staff, settings, audit/events, simulation scenario/reset | shed level <= 3|

Degraded mode: database failures seen by the error handlers raise the shed level for a short
window: 1+ failures in 30 s sheds SUPERVISORY work (reports, staff, settings, audit review,
scenario editing), 5+ also sheds MAIN_FUNCTION. Shed requests get 503 + Retry-After with code
`degraded_mode`; EMERGENCY_SAFETY and MONITORING requests are never shed. SUPERVISORY work also
has a small per-instance concurrency limit so report bursts cannot starve alarm handling.

Vercel functions are stateless and horizontally scaled, so this state is per instance; it is a
defence-in-depth layer, with Vercel Firewall rate limits and Supabase pool limits as primary controls.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from enum import IntEnum
from typing import TypeVar

from psycopg import errors as pg_errors
from starlette.responses import JSONResponse


class OpClass(IntEnum):
    EMERGENCY_SAFETY = 0
    MONITORING = 1
    MAIN_FUNCTION = 2
    SUPERVISORY = 3


# (method regex, path regex, class). First match wins; every API route must match (tested).
ROUTE_CLASSES: list[tuple[str, str, OpClass]] = [
    (r".*", r"^/v1/health$", OpClass.EMERGENCY_SAFETY),
    (r".*", r"^/v1/alarms(/.*)?$", OpClass.EMERGENCY_SAFETY),
    (r".*", r"^/v1/break-glass(/.*)?$", OpClass.EMERGENCY_SAFETY),
    (r".*", r"^/v1/auth(/.*)?$", OpClass.EMERGENCY_SAFETY),
    (r".*", r"^/v1/me(/.*)?$", OpClass.EMERGENCY_SAFETY),
    (r"GET", r"^/v1/simulation$", OpClass.MONITORING),
    (r"POST", r"^/v1/simulation/advance$", OpClass.MONITORING),
    (r".*", r"^/v1/simulation(/.*)?$", OpClass.SUPERVISORY),
    (r"POST", r"^/v1/patients/[^/]+/observations$", OpClass.MAIN_FUNCTION),
    (r".*", r"^/v1/observations(/.*)?$", OpClass.MAIN_FUNCTION),
    (r"GET", r"^/v1/(wards|patients|monitors)(/.*)?$", OpClass.MONITORING),
    (r".*", r"^/v1/(patients|monitors|thresholds|maintenance|files)(/.*)?$", OpClass.MAIN_FUNCTION),
    (r".*", r"^/v1/(reports|staff|settings|events)(/.*)?$", OpClass.SUPERVISORY),
]
_COMPILED = [(re.compile(m), re.compile(p), c) for m, p, c in ROUTE_CLASSES]
DEFAULT_CLASS = OpClass.MAIN_FUNCTION

ESSENTIAL = frozenset({OpClass.EMERGENCY_SAFETY, OpClass.MONITORING})
CONCURRENCY_LIMITS = {OpClass.SUPERVISORY: 5, OpClass.MAIN_FUNCTION: 50}
DEGRADED_WINDOW_SECONDS = 30


def classify(method: str, path: str) -> OpClass | None:
    for m, p, cls in _COMPILED:
        if m.fullmatch(method) and p.match(path):
            return cls
    return None


class _State:
    def __init__(self) -> None:
        self.db_failures: deque[float] = deque(maxlen=100)
        self.forced_level: int | None = None
        self.semaphores = {c: asyncio.Semaphore(n) for c, n in CONCURRENCY_LIMITS.items()}

    def shed_level(self) -> int:
        """Lowest OpClass value that is shed (4 = nothing shed)."""
        if self.forced_level is not None:
            return self.forced_level
        cutoff = time.monotonic() - DEGRADED_WINDOW_SECONDS
        recent = sum(1 for t in self.db_failures if t >= cutoff)
        if recent >= 5:
            return OpClass.MAIN_FUNCTION
        if recent >= 1:
            return OpClass.SUPERVISORY
        return 4

    @property
    def degraded(self) -> bool:
        return self.shed_level() <= OpClass.SUPERVISORY


state = _State()


def note_db_failure() -> None:
    state.db_failures.append(time.monotonic())


def mode() -> dict:
    level = state.shed_level()
    return {"mode": "degraded" if level <= OpClass.SUPERVISORY else "normal",
            "shed_classes": [c.name.lower() for c in OpClass if c >= level and c not in ESSENTIAL]}


def _shed_response(retry_after: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message, "code": "degraded_mode", "degraded": True}, status_code=503,
                        headers={"Retry-After": str(retry_after)})


class PriorityMiddleware:
    """Pure ASGI: classify each request, shed low-priority work in degraded mode, bound concurrency."""

    def __init__(self, app):  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            return await self.app(scope, receive, send)
        found = classify(scope["method"], scope["path"])
        cls = DEFAULT_CLASS if found is None else found  # EMERGENCY_SAFETY == 0 is falsy: compare to None
        scope.setdefault("state", {})["op_class"] = cls
        if cls not in ESSENTIAL and cls >= state.shed_level():
            return await _shed_response(30, "This feature is temporarily unavailable (degraded mode). "
                                            "Monitoring and alarms remain available.")(scope, receive, send)
        sem = state.semaphores.get(cls)
        if sem is None:
            return await self.app(scope, receive, send)
        try:
            await asyncio.wait_for(sem.acquire(), timeout=2)
        except TimeoutError:
            return await _shed_response(15, "The system is busy. Please try again in a moment.")(scope, receive, send)
        try:
            return await self.app(scope, receive, send)
        finally:
            sem.release()


T = TypeVar("T")
RETRYABLE = (pg_errors.DeadlockDetected, pg_errors.LockNotAvailable, pg_errors.SerializationFailure)


async def with_retry(fn: Callable[[], Awaitable[T]], attempts: int = 3, base_delay: float = 0.05) -> T:
    """Run a whole transaction again on deadlock/lock timeout, a bounded number of times (T633)."""
    for attempt in range(attempts):
        try:
            return await fn()
        except RETRYABLE:
            if attempt == attempts - 1:
                raise  # mapped to 503 "busy" by core/errors.py
            await asyncio.sleep(base_delay * 2 ** attempt)
    raise AssertionError("unreachable")
