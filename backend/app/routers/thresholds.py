"""API router: alarm-limit settings (ward defaults and per-patient overrides).

Changing a clinical alarm limit is a high-sensitivity transaction: physician/admin only,
plausibility-checked server-side, explicitly confirmed, and audited with old/new values.

All SQL is static text with bound parameters. The two scopes (ward default / patient override)
use two fixed, fully written-out statement pairs selected from a closed mapping, so no SQL is
ever assembled from request data (T101).
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.audit import record_event
from app.core.security import Perm, Principal, require, require_recent_auth
from app.db import fetch_all, fetch_one, transaction
from app.schemas import MAX_OFFSET, MAX_PAGE_SIZE, Page, ThresholdOut, ThresholdUpdate
from app.services import alarms as alarm_service

router = APIRouter(prefix="/v1/thresholds", tags=["thresholds"])
# Changing a clinical alarm limit: permission + step-up re-authentication within STEP_UP_MAX_AGE.
LimitEditor = Annotated[Principal, Depends(require_recent_auth(Perm.THRESHOLD_WRITE))]

Scope = Literal["ward", "patient"]

_RETURNING = "returning id, ward_id, patient_id, parameter::text as parameter, low_limit, high_limit, updated_at"

_CURRENT_SQL: dict[Scope, str] = {
    "ward": """select low_limit, high_limit from public.alarm_thresholds
               where ward_id = %s and patient_id is null and parameter = %s::public.vital_parameter for update""",
    "patient": """select low_limit, high_limit from public.alarm_thresholds
                  where patient_id = %s and ward_id is null and parameter = %s::public.vital_parameter for update""",
}

_UPSERT_SQL: dict[Scope, str] = {
    "ward": """insert into public.alarm_thresholds (ward_id, parameter, low_limit, high_limit, updated_by)
               values (%s, %s::public.vital_parameter, %s, %s, %s)
               on conflict (ward_id, parameter) where patient_id is null
               do update set low_limit = excluded.low_limit, high_limit = excluded.high_limit,
                             updated_by = excluded.updated_by, updated_at = now()
               """ + _RETURNING,
    "patient": """insert into public.alarm_thresholds (patient_id, parameter, low_limit, high_limit, updated_by)
                  values (%s, %s::public.vital_parameter, %s, %s, %s)
                  on conflict (patient_id, parameter) where ward_id is null
                  do update set low_limit = excluded.low_limit, high_limit = excluded.high_limit,
                                updated_by = excluded.updated_by, updated_at = now()
                  """ + _RETURNING,
}


@router.get("", response_model=Page[ThresholdOut])
async def list_thresholds(principal: Annotated[Principal, Depends(require(Perm.ALARM_READ))],
                          ward_id: UUID | None = None, patient_id: UUID | None = None,
                          limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
                          offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0) -> Page[ThresholdOut]:
    async with transaction(principal, read_only=True) as conn:
        rows = await fetch_all(conn, """select id, ward_id, patient_id, parameter::text as parameter, low_limit, high_limit, updated_at
               from public.alarm_thresholds
               where (%(w)s::uuid is null or ward_id = %(w)s::uuid) and (%(p)s::uuid is null or patient_id = %(p)s::uuid)
               order by parameter, id limit %(limit)s offset %(offset)s""",
                               {"w": str(ward_id) if ward_id else None, "p": str(patient_id) if patient_id else None,
                                "limit": limit + 1, "offset": offset})
    return Page[ThresholdOut](items=[ThresholdOut(**r) for r in rows[:limit]],
                              next_offset=offset + limit if len(rows) > limit else None)


async def _upsert(conn, principal, request, scope: Scope, scope_id: UUID, body: ThresholdUpdate) -> ThresholdOut:
    old = await fetch_one(conn, _CURRENT_SQL[scope], (str(scope_id), body.parameter.value))
    row = await fetch_one(conn, _UPSERT_SQL[scope],
                          (str(scope_id), body.parameter.value, body.low_limit, body.high_limit, str(principal.user_id)))
    if row is None:
        raise HTTPException(404, "Not found.")
    # Re-seal the integrity MAC in the same transaction, so the alarm engine trusts this legitimate change
    # (rows changed outside the API keep a stale MAC and fall back to safe defaults).
    await conn.execute("update public.alarm_thresholds set integrity_mac = %s where id = %s",
                       (alarm_service.threshold_mac(row), str(row["id"])))
    await record_event(principal, "threshold.changed", scope, str(scope_id),
                       details={"parameter": body.parameter.value, "old": old, "new": [body.low_limit, body.high_limit]},
                       conn=conn, request_id=request.state.request_id)
    return ThresholdOut(**row)


@router.put("/wards/{ward_id}", response_model=ThresholdOut)
async def set_ward_threshold(ward_id: UUID, body: ThresholdUpdate, request: Request, principal: LimitEditor) -> ThresholdOut:
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.wards where id = %s and public.can_access_ward(id)", (str(ward_id),)) is None:
            raise HTTPException(404, "Ward not found.")
        return await _upsert(conn, principal, request, "ward", ward_id, body)


@router.put("/patients/{patient_id}", response_model=ThresholdOut)
async def set_patient_threshold(patient_id: UUID, body: ThresholdUpdate, request: Request,
                                principal: LimitEditor) -> ThresholdOut:

    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.patients where id = %s", (str(patient_id),)) is None:
            raise HTTPException(404, "Patient not found.")
        return await _upsert(conn, principal, request, "patient", patient_id, body)
