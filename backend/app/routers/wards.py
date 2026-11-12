"""API router: wards overview and the beds of a ward.

Scope is decided in SQL by the shared helpers (no role literals here): staff see the wards they are
assigned to (administrators all wards, via can_access_ward); device custodians (maintenance:write) see
every ward because monitors move between wards. Counts are computed under RLS for the caller.

``GET /v1/wards/{ward_id}/beds`` gives the Devices screen the beds of a ward with their occupancy (bound
monitor, admitted patient pseudonym), so the SPA never reads the beds table directly. A ward outside the
caller's scope returns the same 404 as a missing one.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.security import Perm, Principal, not_found, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import MAX_OFFSET, MAX_PAGE_SIZE, BedOut, Page, WardOut

router = APIRouter(prefix="/v1/wards", tags=["wards"])


@router.get("", response_model=Page[WardOut])
async def list_wards(principal: Annotated[Principal, Depends(require(Perm.ALARM_READ))],
                     limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
                     offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0) -> Page[WardOut]:
    async with transaction(principal, read_only=True) as conn:
        rows = await fetch_all(conn, """
            select w.id, w.code, w.name,
                   (select count(*) from public.beds b where b.ward_id = w.id)::int as bed_count,
                   (select count(*) from public.patients p where p.ward_id = w.id and p.discharged_at is null)::int as patient_count,
                   (select count(*) from public.alarms a join public.patients p on p.id = a.patient_id
                     where p.ward_id = w.id and a.state = 'active')::int as active_alarms
            from public.wards w
            where (public.can_access_ward(w.id) or public.has_permission('maintenance:write'))
            order by w.code, w.id limit %s offset %s""", (limit + 1, offset))
    return Page[WardOut](items=[WardOut(**r) for r in rows[:limit]],
                         next_offset=offset + limit if len(rows) > limit else None)


@router.get("/{ward_id}/beds", response_model=Page[BedOut])
async def list_beds(ward_id: UUID, principal: Annotated[Principal, Depends(require(Perm.DEVICE_READ))],
                    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
                    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0) -> Page[BedOut]:
    async with transaction(principal, read_only=True) as conn:
        ward = await fetch_one(conn, """select 1 from public.wards w where w.id = %s
               and (public.can_access_ward(w.id) or public.has_permission('maintenance:write'))""", (str(ward_id),))
        if ward is None:
            raise not_found("Ward")
        rows = await fetch_all(conn, """
            select b.id, b.ward_id, b.label, p.id as patient_id, p.pseudonym as patient_pseudonym,
                   m.id as monitor_id, m.serial as monitor_serial
            from public.beds b
            left join public.patients p on p.bed_id = b.id and p.discharged_at is null
            left join public.monitor_assignments ma on ma.bed_id = b.id and ma.unassigned_at is null
            left join public.monitors m on m.id = ma.monitor_id
            where b.ward_id = %s
            order by b.label, b.id limit %s offset %s""", (str(ward_id), limit + 1, offset))
    return Page[BedOut](items=[BedOut(**r, occupied=r.get("monitor_id") is not None) for r in rows[:limit]],
                        next_offset=offset + limit if len(rows) > limit else None)
