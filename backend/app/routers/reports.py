"""API router: aggregate ward activity reports (generated in Python)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.audit import record_event
from app.core.security import Perm, Principal, require
from app.db import transaction
from app.schemas import ReportOut
from app.services import reports

router = APIRouter(prefix="/v1/reports", tags=["reports"])


@router.get("/ward-activity", response_model=ReportOut)
async def ward_activity(request: Request, principal: Annotated[Principal, Depends(require(Perm.REPORT_READ))],
                        ward_id: UUID | None = None, hours: int = 24) -> ReportOut:
    if not 1 <= hours <= 24 * 31:
        raise HTTPException(422, "hours must be between 1 and 744.")
    end = datetime.now(UTC)
    async with transaction(principal) as conn:
        data = await reports.ward_activity(conn, str(ward_id) if ward_id else None, end - timedelta(hours=hours), end)
        await record_event(principal, "report.generated", "report", "ward_activity",
                           details={"ward_id": str(ward_id) if ward_id else None, "hours": hours}, conn=conn,
                           request_id=request.state.request_id)
    return ReportOut(**data)
