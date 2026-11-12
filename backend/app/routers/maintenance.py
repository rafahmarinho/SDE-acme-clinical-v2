"""API router: monitor maintenance tracking (biomedical technicians)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.audit import record_event
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import MaintenanceIn, MaintenanceOut

router = APIRouter(prefix="/v1/monitors/{monitor_id}/maintenance", tags=["maintenance"])

_SELECT = """select r.id, r.monitor_id, r.kind, r.notes, r.performed_at, r.next_due, sp.full_name as performed_by_name
             from public.maintenance_records r join public.staff_profiles sp on sp.user_id = r.performed_by"""


@router.get("", response_model=list[MaintenanceOut])
async def list_maintenance(monitor_id: UUID,
                           principal: Annotated[Principal, Depends(require(Perm.MAINTENANCE_WRITE))]) -> list[MaintenanceOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, _SELECT + " where r.monitor_id = %s order by r.performed_at desc limit 100", (str(monitor_id),))
    return [MaintenanceOut(**r) for r in rows]


@router.post("", response_model=MaintenanceOut, status_code=201)
async def add_maintenance(monitor_id: UUID, body: MaintenanceIn, request: Request,
                          principal: Annotated[Principal, Depends(require(Perm.MAINTENANCE_WRITE))]) -> MaintenanceOut:
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.monitors where id = %s", (str(monitor_id),)) is None:
            raise HTTPException(404, "Monitor not found.")
        row = await fetch_one(conn, """insert into public.maintenance_records (monitor_id, kind, notes, performed_by, next_due)
               values (%s, %s, %s, %s, %s) returning id""",
                              (str(monitor_id), body.kind.value, body.notes, str(principal.user_id), body.next_due))
        if body.kind.value == "battery_replacement":
            await conn.execute("update public.monitors set battery_pct = 100 where id = %s", (str(monitor_id),))
        await record_event(principal, "maintenance.recorded", "monitor", str(monitor_id), details={"kind": body.kind.value},
                           conn=conn, request_id=request.state.request_id)
        out = await fetch_one(conn, _SELECT + " where r.id = %s", (str(row["id"]),))
    return MaintenanceOut(**out)
