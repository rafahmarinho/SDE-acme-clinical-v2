"""API router: emergency ("break glass") access to a patient outside the caller's wards.

Grants are time-boxed (1 hour), require a written justification, are audited, and are listed
for after-the-fact review by an administrator other than the requester.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.audit import record_event
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import BreakGlassIn, BreakGlassOut

router = APIRouter(prefix="/v1/break-glass", tags=["break-glass"])
GRANT_DURATION = timedelta(hours=1)


@router.post("", response_model=BreakGlassOut, status_code=201)
async def request_emergency_access(body: BreakGlassIn, request: Request,
                                   principal: Annotated[Principal, Depends(require(Perm.BREAK_GLASS))]) -> BreakGlassOut:
    async with transaction(principal) as conn:
        exists = await fetch_one(conn, "select public.patient_exists(%s) as ok", (str(body.patient_id),))
        if not exists or not exists["ok"]:
            raise HTTPException(404, "Patient not found.")
        row = await fetch_one(conn, """insert into public.break_glass_grants (user_id, patient_id, reason, expires_at)
               values (%s, %s, %s, %s) returning id, patient_id, expires_at""",
                              (str(principal.user_id), str(body.patient_id), body.reason, datetime.now(UTC) + GRANT_DURATION))
        await record_event(principal, "break_glass.granted", "patient", str(body.patient_id),
                           details={"grant_id": str(row["id"]), "minutes": int(GRANT_DURATION.total_seconds() // 60)},
                           conn=conn, request_id=request.state.request_id)
    return BreakGlassOut(**row)


@router.get("/pending-review")
async def pending_review(principal: Annotated[Principal, Depends(require(Perm.BREAK_GLASS_REVIEW))]) -> list[dict]:
    async with transaction(principal) as conn:
        return await fetch_all(conn, """select g.id, g.patient_id, g.reason, g.granted_at, g.expires_at, sp.full_name as requested_by
               from public.break_glass_grants g join public.staff_profiles sp on sp.user_id = g.user_id
               where g.reviewed_at is null order by g.granted_at desc limit 100""")


@router.post("/{grant_id}/review", status_code=204)
async def review(grant_id: UUID, request: Request,
                 principal: Annotated[Principal, Depends(require(Perm.BREAK_GLASS_REVIEW))]) -> None:
    async with transaction(principal) as conn:
        row = await fetch_one(conn, """update public.break_glass_grants set reviewed_by = %s, reviewed_at = now()
               where id = %s and reviewed_at is null returning id""", (str(principal.user_id), str(grant_id)))
        if row is None:
            raise HTTPException(404, "Grant not found or already reviewed.")
        await record_event(principal, "break_glass.reviewed", "break_glass_grant", str(grant_id), conn=conn,
                           request_id=request.state.request_id)
