"""API router: patients (list with search/filters, detail, readings).

Object-level authorization: every lookup runs under RLS (can_access_patient) and returns 404
for records the caller may not see, so identifiers cannot be enumerated.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import get_settings
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import Page, PatientOut, ReadingOut, SearchText

router = APIRouter(prefix="/v1/patients", tags=["patients"])
Reader = Annotated[Principal, Depends(require(Perm.PATIENT_READ))]

_BASE = """
    select p.id, p.pseudonym, p.display_name, p.birth_year, p.ward_id, p.admitted_at, b.label as bed_label,
           m.serial as monitor_serial,
           (select count(*) from public.alarms a where a.patient_id = p.id and a.state = 'active')::int as active_alarms
    from public.patients p
    left join public.beds b on b.id = p.bed_id
    left join public.monitor_assignments ma on ma.bed_id = p.bed_id and ma.unassigned_at is null
    left join public.monitors m on m.id = ma.monitor_id
"""


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=Page[PatientOut])
async def list_patients(
    principal: Reader,
    q: Annotated[SearchText | None, Query()] = None,
    ward_id: UUID | None = None,
    alarming: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> Page[PatientOut]:
    limit = min(limit, get_settings().max_page_size)
    params: dict = {"ward": str(ward_id) if ward_id else None, "limit": limit + 1, "offset": offset,
                    "q": f"%{_escape_like(q)}%" if q else None, "alarming": alarming}
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, _BASE + """
            where p.discharged_at is null
              and (%(ward)s::uuid is null or p.ward_id = %(ward)s::uuid)
              and (%(q)s::text is null or p.pseudonym ilike %(q)s or p.display_name ilike %(q)s or b.label ilike %(q)s)
              and (%(alarming)s::boolean is null or
                   (exists (select 1 from public.alarms a where a.patient_id = p.id and a.state = 'active')) = %(alarming)s)
            order by p.pseudonym limit %(limit)s offset %(offset)s""", params)
    items = [PatientOut(**r) for r in rows[:limit]]
    return Page[PatientOut](items=items, next_offset=offset + limit if len(rows) > limit else None)


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(patient_id: UUID, principal: Reader) -> PatientOut:
    async with transaction(principal) as conn:
        row = await fetch_one(conn, _BASE + " where p.id = %s", (str(patient_id),))
    if row is None:
        raise HTTPException(404, "Patient not found.")
    return PatientOut(**row)


@router.get("/{patient_id}/readings", response_model=list[ReadingOut])
async def recent_readings(patient_id: UUID, principal: Reader,
                          limit: Annotated[int, Query(ge=1, le=120)] = 60) -> list[ReadingOut]:
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.patients where id = %s", (str(patient_id),)) is None:
            raise HTTPException(404, "Patient not found.")
        rows = await fetch_all(conn, """select recorded_at, heart_rate, spo2, resp_rate, bp_systolic, bp_diastolic, ecg,
               quality::text as quality from public.readings where patient_id = %s order by recorded_at desc limit %s""",
                               (str(patient_id), limit))
    return [ReadingOut(**r) for r in rows]
