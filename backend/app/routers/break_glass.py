"""API router: emergency ("break glass") access to a patient outside the caller's wards.

Procedure (see docs/security/authorization.md):
* Only nurses and physicians (`break_glass:request`) may activate it, after re-authenticating
  recently, explicitly acknowledging the warning and giving a written justification.
* A grant is a separate, time-boxed row (30 minutes) for ONE patient; it is not a role change. It is
  honoured by RLS (`can_access_patient`) only while unexpired and unrevoked, so access ends on the next
  request after expiry or revocation. It covers reading the patient, observations and alarm
  acknowledgement; alarm-limit changes are excluded at the database (`can_configure_thresholds`).
* The requester can end it early; an administrator can revoke it.
* Every grant must be reviewed afterwards by an administrator who is NOT the requester (enforced here,
  by RLS and by a CHECK constraint). Activation, use, revocation and review are audited with the grant id.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg import AsyncConnection
from pydantic import BaseModel, ConfigDict

from app.core.audit import record_event
from app.core.errors import DomainError
from app.core.security import FORBIDDEN, Perm, Principal, not_found, require, require_any, require_recent_auth
from app.db import fetch_all, fetch_one, transaction
from app.schemas import BreakGlassIn, BreakGlassOut

router = APIRouter(prefix="/v1/break-glass", tags=["break-glass"])
GRANT_DURATION = timedelta(minutes=30)
# Re-authentication window for activation: long enough not to delay emergency care, short enough that an
# unattended or hijacked session cannot open another ward's records.
BREAK_GLASS_STEP_UP_MAX_AGE = timedelta(minutes=15)
# Functions available under a grant (documentation of scope; enforced by RLS on each table).
BREAK_GLASS_SCOPE = frozenset({Perm.PATIENT_READ, Perm.OBSERVATION_WRITE, Perm.ALARM_ACK, Perm.FILE_WRITE})


class BreakGlassRequest(BreakGlassIn):
    """Activation request: the warning must be explicitly accepted server-side, not only in the UI."""

    acknowledged_warning: Literal[True]


class BreakGlassReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["appropriate", "inappropriate"]


Requester = Annotated[Principal, Depends(require_recent_auth(Perm.BREAK_GLASS, max_age=BREAK_GLASS_STEP_UP_MAX_AGE))]
Reviewer = Annotated[Principal, Depends(require(Perm.BREAK_GLASS_REVIEW))]


@router.post("", response_model=BreakGlassOut, status_code=201)
async def request_emergency_access(body: BreakGlassRequest, request: Request, principal: Requester) -> BreakGlassOut:
    async with transaction(principal) as conn:
        exists = await fetch_one(conn, "select public.patient_exists(%s) as ok", (str(body.patient_id),))
        if not exists or not exists["ok"]:
            raise not_found("Patient")
        row = await fetch_one(conn, """insert into public.break_glass_grants (user_id, patient_id, reason, expires_at)
               values (%s, %s, %s, %s) returning id, patient_id, expires_at""",
                              (str(principal.user_id), str(body.patient_id), body.reason, datetime.now(UTC) + GRANT_DURATION))
        # The free-text reason is stored on the grant row (reviewable), not copied into the audit details.
        await record_event(principal, "break_glass.granted", "patient", str(body.patient_id),
                           details={"grant_id": str(row["id"]), "minutes": int(GRANT_DURATION.total_seconds() // 60),
                                    "reason_length": len(body.reason), "warning_acknowledged": True},
                           conn=conn, request_id=request.state.request_id)
    return BreakGlassOut(**row)


@router.get("/mine")
async def my_active_grants(principal: Annotated[Principal, Depends(require(Perm.BREAK_GLASS))]) -> dict:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """select id, patient_id, granted_at, expires_at from public.break_glass_grants
               where user_id = %s and revoked_at is null and expires_at > now() order by expires_at desc""",
                               (str(principal.user_id),))
    return {"items": rows}  # JSON object, never a top-level array


@router.post("/{grant_id}/revoke", status_code=204)
async def revoke(grant_id: UUID, request: Request,
                 principal: Annotated[Principal, Depends(require_any(Perm.BREAK_GLASS, Perm.BREAK_GLASS_REVIEW))]) -> None:
    """End a grant early: the requester for their own grant, or a reviewer for anyone else's (RLS-scoped)."""
    async with transaction(principal) as conn:
        row = await fetch_one(conn, """update public.break_glass_grants set revoked_at = now(), revoked_by = %s
               where id = %s and revoked_at is null and expires_at > now() returning id, patient_id""",
                              (str(principal.user_id), str(grant_id)))
        if row is None:
            raise not_found("Active grant")
        await record_event(principal, "break_glass.revoked", "break_glass_grant", str(grant_id),
                           details={"patient_id": str(row["patient_id"])}, conn=conn, request_id=request.state.request_id)


@router.get("/pending")
async def pending_review(principal: Reviewer) -> dict:
    """Grants by other users that still await after-the-fact review."""
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """select g.id, g.patient_id, g.reason, g.granted_at, g.expires_at, g.revoked_at,
                      (g.revoked_at is not null or g.expires_at <= now()) as ended, sp.full_name as requested_by
               from public.break_glass_grants g join public.staff_profiles sp on sp.user_id = g.user_id
               where g.reviewed_at is null and g.user_id <> %s order by g.granted_at desc limit 100""",
                               (str(principal.user_id),))
    return {"items": rows}


@router.post("/{grant_id}/review", status_code=204)
async def review(grant_id: UUID, body: BreakGlassReviewIn, request: Request, principal: Reviewer) -> None:
    async with transaction(principal) as conn:
        grant = await fetch_one(conn, "select user_id, reviewed_at from public.break_glass_grants where id = %s for update",
                                (str(grant_id),))
        if grant is None:
            raise not_found("Grant")
        if str(grant["user_id"]) == str(principal.user_id):  # separation of duties: no self-review
            await record_event(principal, "break_glass.review_denied", "break_glass_grant", str(grant_id),
                               outcome="denied", conn=None, request_id=request.state.request_id)
            raise FORBIDDEN
        if grant["reviewed_at"] is not None:
            raise DomainError("This grant has already been reviewed.")
        row = await fetch_one(conn, """update public.break_glass_grants set reviewed_by = %s, reviewed_at = now(),
               review_outcome = %s where id = %s and reviewed_at is null returning id""",
                              (str(principal.user_id), body.outcome, str(grant_id)))
        if row is None:
            raise HTTPException(404, "Grant not found.")
        await record_event(principal, "break_glass.reviewed", "break_glass_grant", str(grant_id),
                           details={"outcome": body.outcome}, conn=conn, request_id=request.state.request_id)


async def record_break_glass_use(conn: AsyncConnection, principal: Principal, patient_id: UUID | str, action: str,
                                 request_id: str | None = None) -> None:
    """Audit an action on a patient that the caller can reach ONLY through an active break-glass grant.

    Patient-scoped routers call this after a successful read/write (e.g. action="patient.read").
    It is a no-op for normal ward access.
    """
    row = await fetch_one(conn, "select public.active_break_glass_grant(%s) as grant_id", (str(patient_id),))
    if row and row["grant_id"]:
        await record_event(principal, "break_glass.used", "patient", str(patient_id),
                           details={"grant_id": str(row["grant_id"]), "action": action}, conn=conn,
                           request_id=request_id)
