"""API router: alarms (list, acknowledge), monitor states and system status.

* Acknowledging records who/when and an optional note; it never resolves the alarm. The request
  must carry `acknowledged: true` (the user saw the "does not resolve the condition" warning,
  T342) and the response repeats the outcome in `notice`.
* Listing alarms also runs the heartbeat watchdog (T4602) so silent monitors raise
  connection_lost even if pg_cron is unavailable.
* `/monitor-states` gives the predefined per-monitor output (T347): state + stale flag, never
  numeric vitals for a disconnected/faulty monitor.
* `/system-status` tells the UI whether the system is in degraded mode (T433).
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from app.core.audit import record_event
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import AlarmAck, AlarmOut, Out, Page
from app.services import alarms as alarm_service
from app.services import resilience

log = logging.getLogger("acme.alarms")

ACK_NOTICE = ("Alarm acknowledged. Acknowledging does not resolve the condition: the alarm stays active until the "
              "measured value returns within limits. This acknowledgement is recorded with your name and time.")
ALREADY_ACK_NOTICE = "This alarm was already acknowledged. The condition may still be active."

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


class AlarmAckIn(AlarmAck):
    acknowledged: Literal[True] = Field(description="Must be true: the user read that acknowledging does not resolve the condition.")


class AlarmAckOut(AlarmOut):
    notice: str


class MonitorStateOut(Out):
    monitor_id: UUID
    serial: str
    status: str
    battery_pct: int
    last_heartbeat_at: datetime | None
    state: str
    stale: bool
    heartbeat_age_seconds: float | None
    active_alarm_types: list[str]


async def _run_watchdog(conn) -> None:
    """Best effort: a watchdog failure must never prevent clinicians from seeing alarms."""
    try:
        async with conn.transaction():
            await alarm_service.watchdog_sweep(conn)
    except Exception as exc:
        log.error("watchdog_failed", extra={"error_type": type(exc).__name__})


@router.get("", response_model=list[AlarmOut])
async def list_alarms(
    principal: Annotated[Principal, Depends(require(Perm.ALARM_READ))],
    state: Literal["active", "resolved", "all"] = "active",
    ward_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AlarmOut]:
    async with transaction(principal) as conn:
        await _run_watchdog(conn)
        rows = await fetch_all(conn, _SELECT + """
            where (%(state)s = 'all' or a.state::text = %(state)s)
              and (%(ward)s::uuid is null or p.ward_id = %(ward)s::uuid)
            order by (a.state = 'active') desc, array_position(array['high','medium','low'], a.priority::text), a.raised_at desc
            limit %(limit)s""", {"state": state, "ward": str(ward_id) if ward_id else None, "limit": limit})
    return [AlarmOut(**r) for r in rows]


@router.get("/monitor-states", response_model=Page[MonitorStateOut])
async def monitor_states(principal: Annotated[Principal, Depends(require(Perm.ALARM_READ))]) -> Page[MonitorStateOut]:
    async with transaction(principal) as conn:
        await _run_watchdog(conn)
        rows = await fetch_all(conn, """
            select m.id as monitor_id, m.serial, m.status::text as status, m.battery_pct, m.last_heartbeat_at,
                   coalesce(array_agg(a.type::text) filter (where a.id is not null), '{}') as active_alarm_types
            from public.monitors m
            left join public.alarms a on a.monitor_id = m.id and a.state = 'active'
            where m.status <> 'retired'
            group by m.id order by m.serial limit 200""")
    now = datetime.now(UTC)
    return Page[MonitorStateOut](items=[
        MonitorStateOut(**r, **alarm_service.monitor_state(r["status"], r["battery_pct"], r["last_heartbeat_at"], now,
                                                           set(r["active_alarm_types"])))
        for r in rows])


@router.get("/system-status")
async def system_status(principal: Annotated[Principal, Depends(require(Perm.ALARM_READ))]) -> dict:
    """Explicit operating mode for the UI banner; never depends on the database being reachable."""
    return {**resilience.mode(), "checked_at": datetime.now(UTC).isoformat(timespec="milliseconds")}


@router.post("/{alarm_id}/acknowledge", response_model=AlarmAckOut)
async def acknowledge_alarm(alarm_id: UUID, body: AlarmAckIn, request: Request,
                            principal: Annotated[Principal, Depends(require(Perm.ALARM_ACK))]) -> AlarmAckOut:
    async with transaction(principal) as conn:
        existing = await fetch_one(conn, "select id, state::text as state, acknowledged_at from public.alarms where id = %s for update",
                                   (str(alarm_id),))
        if existing is None:
            raise HTTPException(404, "Alarm not found.")
        notice = ALREADY_ACK_NOTICE
        if existing["acknowledged_at"] is None and await alarm_service.acknowledge(
                conn, str(alarm_id), str(principal.user_id), body.note) is not None:
            # Critical audit record: if it cannot be written the acknowledgement is rolled back (503).
            await record_event(principal, "alarm.acknowledged", "alarm", str(alarm_id),
                               details={"state_after": existing["state"], "has_note": bool(body.note)}, conn=conn,
                               request_id=request.state.request_id)
            notice = ACK_NOTICE
        else:
            await record_event(principal, "alarm.ack_rejected", "alarm", str(alarm_id), outcome="failure",
                               error_code="already_acknowledged", conn=conn, request_id=request.state.request_id)
        row = await fetch_one(conn, _SELECT + " where a.id = %s", (str(alarm_id),))
    return AlarmAckOut(**row, notice=notice)


