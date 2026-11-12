"""API router: monitors (devices) and monitor-to-bed binding."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.errors import UniqueViolation

from app.core.audit import record_event
from app.core.errors import DomainError
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import AssignMonitor, MonitorOut

router = APIRouter(prefix="/v1/monitors", tags=["monitors"])

_SELECT = """
    select m.id, m.serial, m.model, m.firmware_version, m.status::text as status, m.battery_pct, m.last_heartbeat_at,
           ma.bed_id, b.label as bed_label, b.ward_id
    from public.monitors m
    left join public.monitor_assignments ma on ma.monitor_id = m.id and ma.unassigned_at is null
    left join public.beds b on b.id = ma.bed_id
"""


@router.get("", response_model=list[MonitorOut])
async def list_monitors(principal: Annotated[Principal, Depends(require(Perm.DEVICE_READ))]) -> list[MonitorOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, _SELECT + " order by m.serial")
    return [MonitorOut(**r) for r in rows]


@router.post("/{monitor_id}/assignment", response_model=MonitorOut)
async def assign_monitor(monitor_id: UUID, body: AssignMonitor, request: Request,
                         principal: Annotated[Principal, Depends(require(Perm.DEVICE_WRITE))]) -> MonitorOut:
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
