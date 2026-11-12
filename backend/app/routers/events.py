"""API router: event / audit log queries and integrity verification."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentPrincipal, Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import EventOut

router = APIRouter(prefix="/v1/events", tags=["events"])


@router.get("", response_model=list[EventOut])
async def list_events(
    principal: CurrentPrincipal,
    action: Annotated[str | None, Query(pattern=r"^[a-z_]+(\.[a-z_]+)?$", max_length=60)] = None,
    entity_type: Annotated[str | None, Query(pattern=r"^[a-z_]+$", max_length=40)] = None,
    before_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[EventOut]:
    # RLS limits non-admins to their own events.
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """
            select id, occurred_at, actor_role::text as actor_role, action, entity_type, entity_id, outcome, details
            from public.events
            where (%(action)s::text is null or action = %(action)s or action like %(prefix)s)
              and (%(etype)s::text is null or entity_type = %(etype)s)
              and (%(before)s::bigint is null or id < %(before)s)
            order by id desc limit %(limit)s""",
                               {"action": action, "prefix": f"{action}.%" if action and "." not in action else "",
                                "etype": entity_type, "before": before_id, "limit": limit})
    return [EventOut(**r) for r in rows]


@router.get("/integrity")
async def verify_integrity(principal: Annotated[Principal, Depends(require(Perm.EVENTS_READ_ALL))]) -> dict:
    async with transaction(principal) as conn:
        row = await fetch_one(conn, "select public.verify_event_chain() as broken_at")
    return {"intact": row["broken_at"] is None, "first_broken_id": row["broken_at"]}
