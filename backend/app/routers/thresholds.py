"""API router: alarm-limit settings (ward defaults and per-patient overrides).

Changing a clinical alarm limit is a high-sensitivity transaction: physician/admin only,
plausibility-checked server-side, explicitly confirmed, and audited with old/new values.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.audit import record_event
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import ThresholdOut, ThresholdUpdate

router = APIRouter(prefix="/v1/thresholds", tags=["thresholds"])


@router.get("", response_model=list[ThresholdOut])
async def list_thresholds(principal: Annotated[Principal, Depends(require(Perm.ALARM_READ))],
                          ward_id: UUID | None = None, patient_id: UUID | None = None) -> list[ThresholdOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """select id, ward_id, patient_id, parameter::text as parameter, low_limit, high_limit, updated_at
               from public.alarm_thresholds
               where (%(w)s::uuid is null or ward_id = %(w)s::uuid) and (%(p)s::uuid is null or patient_id = %(p)s::uuid)
               order by parameter""", {"w": str(ward_id) if ward_id else None, "p": str(patient_id) if patient_id else None})
    return [ThresholdOut(**r) for r in rows]


async def _upsert(conn, principal, request, scope_col: str, scope_id: UUID, body: ThresholdUpdate) -> ThresholdOut:
    assert scope_col in ("ward_id", "patient_id")  # fixed identifiers, never user input
    other = "patient_id" if scope_col == "ward_id" else "ward_id"
    old = await fetch_one(conn, f"select low_limit, high_limit from public.alarm_thresholds where {scope_col} = %s "
                                f"and {other} is null and parameter = %s::public.vital_parameter for update",
                          (str(scope_id), body.parameter.value))
    row = await fetch_one(conn, f"""
        insert into public.alarm_thresholds ({scope_col}, parameter, low_limit, high_limit, updated_by)
        values (%s, %s::public.vital_parameter, %s, %s, %s)
        on conflict ({scope_col}, parameter) where {other} is null
        do update set low_limit = excluded.low_limit, high_limit = excluded.high_limit,
                      updated_by = excluded.updated_by, updated_at = now()
        returning id, ward_id, patient_id, parameter::text as parameter, low_limit, high_limit, updated_at""",
                          (str(scope_id), body.parameter.value, body.low_limit, body.high_limit, str(principal.user_id)))
    if row is None:
        raise HTTPException(404, "Not found.")
    await record_event(principal, "threshold.changed", scope_col.removesuffix("_id"), str(scope_id),
                       details={"parameter": body.parameter.value, "old": old, "new": [body.low_limit, body.high_limit]},
                       conn=conn, request_id=request.state.request_id)
    return ThresholdOut(**row)


@router.put("/wards/{ward_id}", response_model=ThresholdOut)
async def set_ward_threshold(ward_id: UUID, body: ThresholdUpdate, request: Request,
                             principal: Annotated[Principal, Depends(require(Perm.THRESHOLD_WRITE))]) -> ThresholdOut:
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.wards where id = %s and public.can_access_ward(id)", (str(ward_id),)) is None:
            raise HTTPException(404, "Ward not found.")
        return await _upsert(conn, principal, request, "ward_id", ward_id, body)


@router.put("/patients/{patient_id}", response_model=ThresholdOut)
async def set_patient_threshold(patient_id: UUID, body: ThresholdUpdate, request: Request,
                                principal: Annotated[Principal, Depends(require(Perm.THRESHOLD_WRITE))]) -> ThresholdOut:
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.patients where id = %s", (str(patient_id),)) is None:
            raise HTTPException(404, "Patient not found.")
        return await _upsert(conn, principal, request, "patient_id", patient_id, body)
