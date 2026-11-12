"""Monitor (device) authenticity (T425/T426).

Every monitor has a per-device secret ("pairing code", printed on the device label / shown on the
simulated monitor). Only its SHA-256 is stored (public.monitors.device_secret_hash). Binding a monitor
to a bed requires the caller to present the pairing code; the database function
public.verify_monitor_secret() compares hashes and throttles failures per device, shared by every API
instance: 5 failures lock the device for 15 minutes, each further failure after a lock doubles the lock up to
24 hours (0012_device_auth_lockout.sql). "Locked", "unknown" and "wrong secret" are indistinguishable to the
caller; the API audits each failure and alerts administrators on a lockout (LOCKED_SQL). Secrets are issued
by `python -m app.cli provision-monitor-secrets` and shown once; they are never logged, returned by the API or stored in clear.

The pure helpers below are used by the CLI and by tests; the API path uses `verify_in_db`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any
from uuid import UUID

MIN_SECRET_LENGTH = 16
MAX_SECRET_LENGTH = 256


class DeviceAuthError(Exception):
    """The monitor could not prove its identity (unknown, retired, wrong secret or throttled)."""


def new_device_secret() -> tuple[str, bytes]:
    """A fresh pairing code and the SHA-256 digest to store."""
    secret = secrets.token_urlsafe(24)  # 192 bits
    return secret, hash_device_secret(secret)


def hash_device_secret(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def verify_device_secret(presented: str | None, stored_hash: bytes | None, *, status: str = "online") -> bool:
    """Constant-time comparison of SHA-256(presented) with the stored hash; retired devices never verify."""
    if not presented or stored_hash is None or status == "retired":
        return False
    if not MIN_SECRET_LENGTH <= len(presented) <= MAX_SECRET_LENGTH:
        return False
    return hmac.compare_digest(hash_device_secret(presented), bytes(stored_hash))


async def verify_in_db(conn: Any, monitor_id: UUID, presented: str | None) -> None:
    """Raise DeviceAuthError unless the database confirms the monitor's secret (throttled server-side)."""
    from app.db import fetch_one

    if not presented or not MIN_SECRET_LENGTH <= len(presented) <= MAX_SECRET_LENGTH:
        raise DeviceAuthError("device authentication failed")
    row = await fetch_one(conn, "select public.verify_monitor_secret(%s, %s) as ok", (str(monitor_id), presented))
    if not row or not row["ok"]:
        raise DeviceAuthError("device authentication failed")


# Lockout state (for auditing/alerting only, never told to the caller) and the administrator unlock; the
# database refuses the unlock for callers without settings:manage (0012_device_auth_lockout.sql).
LOCKED_SQL = "select public.monitor_auth_locked(%s) as locked"
UNLOCK_SQL = "select public.unlock_monitor_auth(%s) as unlocked"
