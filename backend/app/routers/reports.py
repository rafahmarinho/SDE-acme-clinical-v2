"""API router: aggregate ward activity reports and audit log reduction (generated in Python).

* `/ward-activity` - counts/durations per ward (physician, admin).
* `/audit` - audit log reduction summary (admin only, `events:read_all`), read-only (T437).
* `/export.csv?kind=` - CSV export of an allow-listed report kind via a private temp file that is
  deleted after the response is sent (T157). Formula injection is neutralised; ward counts below the
  small-cell threshold are suppressed exactly as in the JSON report (T544).
* `/research-extract` - de-identified vital-sign extract for secondary use (T377): administrators with
  settings:manage only, Safe Harbor field removal, per-extract keyed subject codes, time offsets instead of
  timestamps, small wards suppressed; audited with row counts only.
Every report generation/export is itself audited (T45).
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.audit import record_event
from app.core.ratelimit import enforce_shared_limit
from app.core.security import Perm, Principal, require
from app.db import fetch_one, transaction
from app.schemas import Out, ReportOut
from app.services import privacy, reports

router = APIRouter(prefix="/v1/reports", tags=["reports"])
ActionFilter = Annotated[str | None, Query(max_length=600, description="Comma-separated action names")]
_ACTION = r"^[a-z_]+\.[a-z_]+$"


class AuditSummaryOut(Out):
    period_start: datetime
    period_end: datetime
    total: int
    truncated: bool
    first_id: int | None
    last_id: int | None
    totals_by_action: dict[str, int]
    totals_by_actor: dict[str, int]
    totals_by_outcome: dict[str, int]
    suspicious_actors: list[str]
    acknowledged_alarms: int
    chain_intact: bool
    chain_first_broken_id: int | None
    generated_at: datetime
    restricted_subjects_excluded: int = 0


class ResearchExtractOut(Out):
    format: Literal["acme-clinical-deidentified-vitals/v1"] = "acme-clinical-deidentified-vitals/v1"
    method: Literal["safe-harbor"] = "safe-harbor"
    period_days: int
    min_subjects_per_ward: int
    columns: list[str]
    rows: list[dict]


def _window(hours: int) -> tuple[datetime, datetime]:
    if not 1 <= hours <= 24 * 31:
        raise HTTPException(422, "hours must be between 1 and 744.")
    end = datetime.now(UTC)
    return end - timedelta(hours=hours), end


def _check_actions(raw: str | None) -> list[str]:
    actions = [a.strip() for a in (raw or "").split(",") if a.strip()]
    if len(actions) > 20 or any(not re.fullmatch(_ACTION, a) or len(a) > 60 for a in actions):
        raise HTTPException(422, "Invalid action filter.")
    return actions


@router.get("/ward-activity", response_model=ReportOut)
async def ward_activity(request: Request, principal: Annotated[Principal, Depends(require(Perm.REPORT_READ))],
                        ward_id: UUID | None = None, hours: int = 24) -> ReportOut:
    start, end = _window(hours)
    async with transaction(principal) as conn:
        await enforce_shared_limit(conn, "reports", fetch_one)
        data = await reports.ward_activity(conn, str(ward_id) if ward_id else None, start, end)
        await record_event(principal, "report.generated", "report", "ward_activity",
                           details={"ward_id": str(ward_id) if ward_id else None, "hours": hours}, conn=conn,
                           request_id=request.state.request_id)
    # Small-cell suppression (privacy): counts below MIN_CELL_SIZE are reported as null, not their value.
    return ReportOut(**{**data, "alarm_counts": privacy.suppress_small_counts(data["alarm_counts"])})


@router.get("/audit", response_model=AuditSummaryOut)
async def audit_report(request: Request, principal: Annotated[Principal, Depends(require(Perm.EVENTS_READ_ALL))],
                       hours: int = 24, actions: ActionFilter = None, actor_id: UUID | None = None,
                       outcome: Literal["success", "denied", "failure"] | None = None) -> AuditSummaryOut:
    start, end = _window(hours)
    actions = _check_actions(actions)
    async with transaction(principal) as conn:
        await enforce_shared_limit(conn, "reports", fetch_one)
        data = await reports.audit_summary(conn, start, end, actions, str(actor_id) if actor_id else None, outcome)
        await record_event(principal, "report.generated", "report", "audit",
                           details={"hours": hours, "actions": len(actions), "outcome": outcome}, conn=conn,
                           request_id=request.state.request_id)
    return AuditSummaryOut(**data)


# The body is a CSV file (documented as binary); FileResponse bypasses model serialization.
@router.get("/export.csv", response_class=FileResponse, response_model=bytes)
async def export_csv(kind: reports.ReportKind, request: Request,
                     principal: Annotated[Principal, Depends(require(Perm.REPORT_READ))],
                     hours: int = 24, ward_id: UUID | None = None) -> FileResponse:
    start, end = _window(hours)
    if kind is reports.ReportKind.audit_events and not principal.can(Perm.EVENTS_READ_ALL):
        from app.core.security import FORBIDDEN

        raise FORBIDDEN
    async with transaction(principal) as conn:
        await enforce_shared_limit(conn, "reports", fetch_one)
        if kind is reports.ReportKind.audit_events:
            columns, rows = reports.AUDIT_COLUMNS, await reports.audit_rows(conn, start, end)
        else:
            data = await reports.ward_activity(conn, str(ward_id) if ward_id else None, start, end)
            columns = ("alarm_type", "count")
            # Same small-cell suppression as the JSON report: counts below MIN_CELL_SIZE are blank, never exact.
            suppressed = privacy.suppress_small_counts(data["alarm_counts"])
            rows = [{"alarm_type": t, "count": n} for t, n in suppressed.items()]
        path, cleanup = reports.build_csv_export(columns, rows)
        try:
            await record_event(principal, "report.exported", "report", kind.value,
                               details={"hours": hours, "rows": len(rows)}, conn=conn, request_id=request.state.request_id)
        except BaseException:
            cleanup()
            raise
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=f"{kind.value}.csv",
                        background=BackgroundTask(cleanup))


@router.get("/research-extract", response_model=ResearchExtractOut)
async def research_extract(request: Request,
                           principal: Annotated[Principal, Depends(require(Perm.REPORT_READ, Perm.SETTINGS_MANAGE))],
                           days: Annotated[int, Query(ge=1, le=31)] = 7) -> ResearchExtractOut:
    """De-identified vital signs for secondary use. Never contains names, pseudonyms, ids, beds, timestamps,
    observation text, ECG traces or file references."""
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    async with transaction(principal) as conn:
        await enforce_shared_limit(conn, "reports", fetch_one)
        rows = await reports.research_extract(conn, start, end, min_subjects=privacy.MIN_CELL_SIZE)
        await record_event(principal, "report.research_extract", "report", "research_extract",
                           details={"days": days, "rows": len(rows),
                                    "subjects": len({r["subject"] for r in rows})},
                           conn=conn, request_id=request.state.request_id)
    return ResearchExtractOut(period_days=days, min_subjects_per_ward=privacy.MIN_CELL_SIZE,
                              columns=list(reports.EXTRACT_COLUMNS), rows=rows)
