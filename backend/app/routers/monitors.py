"""API router: monitors (devices) and monitor-to-bed binding.

Binding is a state change and therefore POST (bind) / DELETE (unbind), never GET (T1542). The
request carries only the bed pointer and an explicit confirmation; who bound it and when are
taken from the verified session and the database (T33).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.errors import UniqueViolation

from app.core.audit import record_event
from app.core.errors import DomainError
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import MAX_OFFSET, MAX_PAGE_SIZE, AssignMonitor, MonitorOut, Page
from app.services import device_auth

PAIRING_FAILED = "The pairing code does not match this monitor (or too many attempts). Check the device label."

router = APIRouter(prefix="/v1/monitors", tags=["monitors"])

_SELECT = """
    select m.id, m.serial, m.model, m.firmware_version, m.status::text as status, m.battery_pct, m.last_heartbeat_at,
           ma.bed_id, b.label as bed_label, b.ward_id
    from public.monitors m
    left join public.monitor_assignments ma on ma.monitor_id = m.id and ma.unassigned_at is null
    left join public.beds b on b.id = ma.bed_id
"""


@router.get("", response_model=Page[MonitorOut])
async def list_monitors(principal: Annotated[Principal, Depends(require(Perm.DEVICE_READ))],
                        limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
                        offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0) -> Page[MonitorOut]:
    async with transaction(principal, read_only=True) as conn:
        rows = await fetch_all(conn, _SELECT + " order by m.serial, m.id limit %s offset %s", (limit + 1, offset))
    return Page[MonitorOut](items=[MonitorOut(**r) for r in rows[:limit]],
                            next_offset=offset + limit if len(rows) > limit else None)


@router.post("/{monitor_id}/assignment", response_model=MonitorOut)
async def assign_monitor(monitor_id: UUID, body: AssignMonitor, request: Request,
                         principal: Annotated[Principal, Depends(require(Perm.DEVICE_WRITE))]) -> MonitorOut:
    # Device authenticity first, in its own transaction, so the failure counter (throttling) and the audit
    # record of a failed attempt are committed even though the request is refused.
    auth_failed = False
    async with transaction(principal) as conn:
        try:
            await device_auth.verify_in_db(conn, monitor_id, body.pairing_code)
        except device_auth.DeviceAuthError:
            auth_failed = True
            await record_event(principal, "monitor.auth_failed", "monitor", str(monitor_id), outcome="failure",
                               error_code="device_auth_failed", conn=conn, request_id=request.state.request_id)
    if auth_failed:
        raise DomainError(PAIRING_FAILED, 403, code="device_auth_failed")
    async with transaction(principal) as conn:
        monitor = await fetch_one(conn, "select id, status::text as status from public.monitors where id = %s for update",
                                  (str(monitor_id),))
        if monitor is None:
            raise HTTPException(404, "Monitor not found.")
        if monitor["status"] in ("maintenance", "retired"):
            raise DomainError("This monitor is not available for clinical use.")

        if await fetch_one(conn, "select 1 from public.beds where id = %s", (str(body.bed_id),)) is None:
            raise HTTPException(404, "Bed not found.")
        await conn.execute("update public.monitor_assignments set unassigned_at = now() where monitor_id = %s and unassigned_at is null",
                           (str(monitor_id),))
        try:
            await conn.execute("insert into public.monitor_assignments (monitor_id, bed_id, assigned_by) values (%s, %s, %s)",
                               (str(monitor_id), str(body.bed_id), str(principal.user_id)))
        except UniqueViolation as exc:
            raise DomainError("That bed already has a monitor. Unbind it first.") from exc
        await record_event(principal, "monitor.bound", "monitor", str(monitor_id), details={"bed_id": str(body.bed_id)},
                           conn=conn, request_id=request.state.request_id)
        row = await fetch_one(conn, _SELECT + " where m.id = %s", (str(monitor_id),))
    return MonitorOut(**row)


@router.delete("/{monitor_id}/assignment", status_code=204)
async def unassign_monitor(monitor_id: UUID, request: Request,
                           principal: Annotated[Principal, Depends(require(Perm.DEVICE_WRITE))]) -> None:
    async with transaction(principal) as conn:
        updated = await fetch_one(conn, """update public.monitor_assignments set unassigned_at = now()
               where monitor_id = %s and unassigned_at is null returning bed_id""", (str(monitor_id),))
        if updated is None:
            raise HTTPException(404, "Monitor is not bound to a bed.")
        await record_event(principal, "monitor.unbound", "monitor", str(monitor_id), details={"bed_id": str(updated["bed_id"])},
                           conn=conn, request_id=request.state.request_id)
