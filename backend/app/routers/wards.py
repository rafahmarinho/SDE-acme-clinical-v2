"""API router: wards overview."""

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
            where public.can_access_ward(w.id) or public.current_staff_role() = 'biomed_tech'
            order by w.code""")
    return [WardOut(**r) for r in rows]
