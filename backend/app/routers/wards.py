"""API router: wards overview.

Scope is decided in SQL by the shared helpers (no role literals here): staff see the wards they are
assigned to (administrators all wards, via can_access_ward); device custodians (maintenance:write) see
every ward because monitors move between wards. Counts are computed under RLS for the caller.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import Perm, Principal, require
from app.db import fetch_all, transaction
from app.schemas import WardOut

router = APIRouter(prefix="/v1/wards", tags=["wards"])


@router.get("", response_model=list[WardOut])
async def list_wards(principal: Annotated[Principal, Depends(require(Perm.ALARM_READ))]) -> list[WardOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """
            select w.id, w.code, w.name,
                   (select count(*) from public.beds b where b.ward_id = w.id)::int as bed_count,
                   (select count(*) from public.patients p where p.ward_id = w.id and p.discharged_at is null)::int as patient_count,
                   (select count(*) from public.alarms a join public.patients p on p.id = a.patient_id
                     where p.ward_id = w.id and a.state = 'active')::int as active_alarms
            from public.wards w
            where public.can_access_ward(w.id) or public.has_permission('maintenance:write')
            order by w.code""")
    return [WardOut(**r) for r in rows]
