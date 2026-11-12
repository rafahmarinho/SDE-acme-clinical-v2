"""Database access layer: parameterized queries via the least-privilege `acme_api` role.

Every request that touches data runs inside `transaction(principal)`, which sets the
transaction-local `app.user_id` / `app.role` settings consumed by the row-level-security
policies in supabase/migrations/0002_roles_rls.sql. SQL is always parameterized (psycopg
placeholders); identifiers are never built from user input.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings

_pool: AsyncConnectionPool | None = None


def _get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url.get_secret_value(),
            min_size=0,
            max_size=5,
            timeout=5,
            max_idle=60,
            open=False,
            kwargs={"row_factory": dict_row, "connect_timeout": 5, "application_name": "acme-clinical-api"},
        )
    return _pool


async def open_pool() -> None:
    await _get_pool().open()


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def transaction(principal: Any | None, *, read_only: bool = False) -> AsyncIterator[AsyncConnection]:
    """Yield a connection inside a transaction scoped to the caller's identity (connections are always returned).

    ``read_only=True`` (pure GET handlers) makes PostgreSQL refuse any write in the transaction, so a bug or an
    injected statement in a read path cannot modify data.
    """
    async with _get_pool().connection() as conn:
        async with conn.transaction():
            if read_only:
                await conn.execute("set transaction read only")
            if principal is not None:
                await conn.execute(
                    "select set_config('app.user_id', %s, true), set_config('app.role', %s, true)",
                    (str(principal.user_id), principal.role.value),
                )
            yield conn


async def fetch_all(conn: AsyncConnection, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[dict]:
    async with conn.cursor() as cur:
        await cur.execute(sql, params)  # type: ignore[arg-type]
        return list(await cur.fetchall())


async def fetch_one(conn: AsyncConnection, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> dict | None:
    async with conn.cursor() as cur:
        await cur.execute(sql, params)  # type: ignore[arg-type]
        return await cur.fetchone()


async def execute(conn: AsyncConnection, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> int:
    async with conn.cursor() as cur:
        await cur.execute(sql, params)  # type: ignore[arg-type]
        return cur.rowcount


async def fetch_staff_identity(user_id: UUID) -> dict | None:
    async with transaction(None) as conn:
        row = await fetch_one(conn, "select * from public.staff_identity(%s)", (str(user_id),))
    if row is None:
        return None
    return {
        "email": row["email"],
        "role": row["role"],
        "is_active": row["is_active"],
        "security": {
            "session_idle_minutes": row["session_idle_minutes"],
            "session_absolute_hours": row["session_absolute_hours"],
            "max_concurrent_sessions": row["max_concurrent_sessions"],
            "require_mfa_for_admin": row["require_mfa_for_admin"],
        },
    }
