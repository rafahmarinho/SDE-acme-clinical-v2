"""API router: clinical observations for a patient."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.audit import record_event
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import MAX_OFFSET, MAX_PAGE_SIZE, ObservationIn, ObservationOut, Page

router = APIRouter(prefix="/v1/patients/{patient_id}/observations", tags=["observations"])


@router.get("", response_model=Page[ObservationOut])
async def list_observations(patient_id: UUID, principal: Annotated[Principal, Depends(require(Perm.PATIENT_READ))],
                            limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
                            offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0) -> Page[ObservationOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """select o.id, o.body, o.created_at, sp.full_name as author_name
               from public.observations o join public.staff_profiles sp on sp.user_id = o.author_id
               where o.patient_id = %s order by o.created_at desc, o.id limit %s offset %s""",
                               (str(patient_id), limit + 1, offset))
    return Page[ObservationOut](items=[ObservationOut(**r) for r in rows[:limit]],
                                next_offset=offset + limit if len(rows) > limit else None)


@router.post("", response_model=ObservationOut, status_code=201)
async def add_observation(patient_id: UUID, body: ObservationIn, request: Request,
                          principal: Annotated[Principal, Depends(require(Perm.OBSERVATION_WRITE))]) -> ObservationOut:
    # Author, patient and timestamp are server-owned: author from the verified session, patient from the
    # path (checked under RLS), created_at from the database. The body carries only the observation text.
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.patients where id = %s", (str(patient_id),)) is None:
            raise HTTPException(404, "Patient not found.")
        row = await fetch_one(conn, """insert into public.observations (patient_id, author_id, body)
               values (%s, %s, %s) returning id, body, created_at""", (str(patient_id), str(principal.user_id), body.body))
        await record_event(principal, "observation.created", "patient", str(patient_id),
                           details={"observation_id": str(row["id"]), "length": len(body.body)}, conn=conn,
                           request_id=request.state.request_id)
        name = await fetch_one(conn, "select full_name from public.staff_profiles where user_id = %s", (str(principal.user_id),))
    return ObservationOut(**row, author_name=name["full_name"] if name else "")
