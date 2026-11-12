"""Staff identity helpers shared by registration (team management), the CLI and tests.

One username rule for every subsystem (T286/T287): a staff username is the e-mail address, ASCII only,
stored lower-case; leading/trailing whitespace and invisible/control characters are rejected by the API
(the UI trims before calling Supabase Auth). The same rule is implemented in
frontend/src/lib/authPolicy.ts (canonicalEmail) and in the staff_profiles_email_canonical constraint
(supabase/migrations/0006_auth.sql). Authorization always keys on the auth.users UUID, never on e-mail.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import time
import unicodedata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def canonical_email(raw: str) -> str:
    """Canonical form of a staff e-mail address, or ValueError if it is not acceptable."""
    if raw != raw.strip() or any(unicodedata.category(c) in ("Cf", "Cc", "Zs", "Zl", "Zp") for c in raw):
        raise ValueError("Email must not contain spaces or invisible characters.")
    if not raw.isascii():
        raise ValueError("Only ASCII email addresses are accepted.")
    value = raw.lower()
    if len(value) > 254 or not _EMAIL.fullmatch(value):
        raise ValueError("Enter a valid email address.")
    return value


# ---------------------------------------------------------------------------
# Uniform response time for app-owned endpoints that touch identity (T73)
# ---------------------------------------------------------------------------
AUTH_TIMING_FLOOR_S = 0.4   # longer than the slowest legitimate path (Supabase Admin API round trip)
AUTH_TIMING_JITTER_MS = 200


@asynccontextmanager
async def uniform_auth_timing(floor_s: float = AUTH_TIMING_FLOOR_S, jitter_ms: int = AUTH_TIMING_JITTER_MS) -> AsyncIterator[None]:
    """Every exit (success or error) takes at least ``floor_s`` plus random jitter from `secrets`.

    Uses asyncio.sleep so the worker is never blocked. Supabase Auth's own login endpoint cannot be
    wrapped (the browser calls it directly); it relies on platform rate limits and the lockout hook.
    """
    start = time.monotonic()
    try:
        yield
    finally:
        target = floor_s + secrets.randbelow(max(jitter_ms, 1)) / 1000
        remaining = target - (time.monotonic() - start)
        if remaining > 0:
            await asyncio.sleep(remaining)
