"""API router: alarms (list, acknowledge).

Acknowledging records who/when and an optional note; it never resolves the alarm.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.audit import record_event
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import AlarmAck, AlarmOut
from app.services import alarms as alarm_service

router = APIRouter(prefix="/v1/alarms", tags=["alarms"])

_SELECT = """
    select a.id, a.patient_id, p.pseudonym as patient_pseudonym, m.serial as monitor_serial, a.type::text as type,
           a.priority::text as priority, a.state::text as state, a.message, a.raised_at, a.last_seen_at,
           a.resolved_at, a.acknowledged_at, ack.full_name as acknowledged_by_name
    from public.alarms a
    join public.monitors m on m.id = a.monitor_id
    left join public.patients p on p.id = a.patient_id
    left join public.staff_profiles ack on ack.user_id = a.acknowledged_by
"""


@router.get("", response_model=list[AlarmOut])
async def list_alarms(
    principal: Annotated[Principal, Depends(require(Perm.ALARM_READ))],
    state: Literal["active", "resolved", "all"] = "active",
    ward_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AlarmOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, _SELECT + """
            where (%(state)s = 'all' or a.state::text = %(state)s)
              and (%(ward)s::uuid is null or p.ward_id = %(ward)s::uuid)
            order by (a.state = 'active') desc, array_position(array['high','medium','low'], a.priority::text), a.raised_at desc
            limit %(limit)s""", {"state": state, "ward": str(ward_id) if ward_id else None, "limit": limit})
    return [AlarmOut(**r) for r in rows]


@router.post("/{alarm_id}/acknowledge", response_model=AlarmOut)
async def acknowledge_alarm(alarm_id: UUID, body: AlarmAck, request: Request,
                            principal: Annotated[Principal, Depends(require(Perm.ALARM_ACK))]) -> AlarmOut:
    async with transaction(principal) as conn:
        existing = await fetch_one(conn, "select id, state::text as state, acknowledged_at from public.alarms where id = %s for update",
                                   (str(alarm_id),))
        if existing is None:
            raise HTTPException(404, "Alarm not found.")
        if existing["acknowledged_at"] is None:
            await alarm_service.acknowledge(conn, str(alarm_id), str(principal.user_id), body.note)
            await record_event(principal, "alarm.acknowledged", "alarm", str(alarm_id),
                               details={"state_after": existing["state"], "has_note": bool(body.note)}, conn=conn,
                               request_id=request.state.request_id)
        row = await fetch_one(conn, _SELECT + " where a.id = %s", (str(alarm_id),))
    return AlarmOut(**row)
