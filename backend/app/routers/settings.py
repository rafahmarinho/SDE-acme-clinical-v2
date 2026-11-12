"""API router: unified, administrator-only security settings interface (T371/T2273).

One place for every security parameter: the database-managed settings (bounded by Pydantic and by
CHECK constraints so they can never drop below the secure baseline), the read-only environment flags,
the component inventory, a tamper-evidence fingerprint with an "approve configuration" action, the data
retention controls (T607) and the staff erasure-request queue (T179). Every route requires
`settings:manage` (or `staff:manage` for erasure requests): other roles get 403 for read AND write.
Every change is audited; audit details carry identifiers and enumerated values only.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator

from app.core.audit import record_event
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import SecuritySettingsOut, SecuritySettingsUpdate, Strict
from app.services import privacy

router = APIRouter(prefix="/v1/settings", tags=["settings"])
log = logging.getLogger("acme.settings")

_COLUMNS = ("password_min_length", "session_idle_minutes", "session_absolute_hours", "max_concurrent_sessions",
            "lockout_threshold", "lockout_minutes", "require_mfa_for_admin", "data_retention_days")

SettingsAdmin = Annotated[Principal, Depends(require(Perm.SETTINGS_MANAGE))]
StaffAdmin = Annotated[Principal, Depends(require(Perm.STAFF_MANAGE))]


class SecurityReport(BaseModel):
    settings: SecuritySettingsOut
    fingerprint: str
    approved_fingerprint: str | None
    approved_at: datetime | None
    drift: bool
    environment: dict[str, Any]
    components: dict[str, str]
    generated_at: datetime


class ApprovalOut(BaseModel):
    fingerprint: str
    approved_at: datetime


class PurgeRun(BaseModel):
    run_at: datetime
    run_source: Literal["scheduled", "manual"]
    counts: dict[str, int | None]


class RetentionOut(BaseModel):
    data_retention_days: int
    schedule: str = "Daily at 03:15 UTC (pg_cron job acme-retention-purge)"
    files_pending_removal: int
    items: list[PurgeRun]


class RetentionRunIn(Strict):
    confirm_text: Annotated[str, Field(max_length=40)]

    @model_validator(mode="after")
    def _typed(self) -> RetentionRunIn:
        if self.confirm_text != "PURGE EXPIRED DATA":
            raise ValueError("type PURGE EXPIRED DATA to confirm")
        return self


class RetentionRunOut(BaseModel):
    counts: dict[str, int | None]
    files_removed: int
    files_pending_removal: int


class PrivacyRequestOut(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str
    kind: Literal["erasure"]
    status: Literal["pending", "completed", "rejected"]
    requested_at: datetime
    decided_at: datetime | None


class PrivacyRequestPage(BaseModel):
    items: list[PrivacyRequestOut]


class ErasureCompleteIn(Strict):
    confirm_text: Annotated[str, Field(max_length=40)]

    @model_validator(mode="after")
    def _typed(self) -> ErasureCompleteIn:
        if self.confirm_text != "ERASE":
            raise ValueError("type ERASE to confirm")
        return self


class ErasureDecisionOut(BaseModel):
    id: UUID
    status: Literal["completed", "rejected"]
    identity_provider_scrubbed: bool | None = None


# ---------------------------------------------------------------------------
# Database-managed security settings
# ---------------------------------------------------------------------------
@router.get("/security", response_model=SecuritySettingsOut)
async def get_security_settings(principal: SettingsAdmin) -> SecuritySettingsOut:
    async with transaction(principal) as conn:
        row = await fetch_one(conn, "select * from public.security_settings where id = 1")
    return SecuritySettingsOut(**row)


@router.patch("/security", response_model=SecuritySettingsOut)
async def update_security_settings(body: SecuritySettingsUpdate, request: Request,
                                   principal: SettingsAdmin) -> SecuritySettingsOut:
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items() if k in _COLUMNS}
    async with transaction(principal) as conn:
        before = await fetch_one(conn, "select * from public.security_settings where id = 1 for update")
        for column, value in changes.items():  # column names come from the fixed allow-list above
            await conn.execute(f"update public.security_settings set {column} = %s, updated_by = %s where id = 1",
                               (value, str(principal.user_id)))
        await record_event(principal, "settings.security_changed", "security_settings", "1",
                           details={k: [before[k], v] for k, v in changes.items()}, conn=conn,
                           request_id=request.state.request_id)
        row = await fetch_one(conn, "select * from public.security_settings where id = 1")
    return SecuritySettingsOut(**row)


@router.get("/security/report", response_model=SecurityReport)
async def security_report(request: Request, principal: SettingsAdmin) -> SecurityReport:
    """Effective configuration, approved baseline and drift (out-of-band changes are detected here)."""
    async with transaction(principal) as conn:
        row = await fetch_one(conn, "select * from public.security_settings where id = 1")
        approved = await fetch_one(conn, """select fingerprint, approved_at from public.security_settings_approvals
               order by id desc limit 1""")
        await record_event(principal, "settings.report_viewed", "security_settings", "1", conn=conn,
                           request_id=request.state.request_id)
    current = privacy.config_fingerprint(row)
    return SecurityReport(
        settings=SecuritySettingsOut(**row), fingerprint=current,
        approved_fingerprint=approved["fingerprint"] if approved else None,
        approved_at=approved["approved_at"] if approved else None,
        drift=approved is None or approved["fingerprint"] != current,
        environment=privacy.environment_flags(get_settings()), components=privacy.component_versions(),
        generated_at=datetime.now(UTC))


@router.post("/security/approve", response_model=ApprovalOut, status_code=201)
async def approve_configuration(request: Request, principal: SettingsAdmin) -> ApprovalOut:
    """Record the current settings as the approved baseline (four-eyes review happens in the change PR/ticket)."""
    async with transaction(principal) as conn:
        row = await fetch_one(conn, "select * from public.security_settings where id = 1 for share")
        fingerprint = privacy.config_fingerprint(row)
        saved = await fetch_one(conn, """insert into public.security_settings_approvals (fingerprint, approved_by)
               values (%s, %s) returning fingerprint, approved_at""", (fingerprint, str(principal.user_id)))
        await record_event(principal, "settings.configuration_approved", "security_settings", "1",
                           details={"fingerprint": fingerprint[:16]}, conn=conn, request_id=request.state.request_id)
    return ApprovalOut(**saved)


# ---------------------------------------------------------------------------
# Retention (automated destruction of personal data that is no longer needed)
# ---------------------------------------------------------------------------
async def _pending_files(conn) -> int:
    row = await fetch_one(conn, "select count(*)::int as n from public.storage_purge_queue")
    return row["n"] if row else 0


@router.get("/retention", response_model=RetentionOut)
async def retention_status(principal: SettingsAdmin,
                           limit: Annotated[int, Query(ge=1, le=50)] = 10) -> RetentionOut:
    async with transaction(principal) as conn:
        days = await fetch_one(conn, "select data_retention_days from public.security_settings where id = 1")
        runs = await fetch_all(conn, """select run_at, run_source, counts from public.purge_log
               order by id desc limit %s""", (limit,))
        pending = await _pending_files(conn)
    return RetentionOut(data_retention_days=days["data_retention_days"] if days else 365,
                        files_pending_removal=pending, items=[PurgeRun(**r) for r in runs])


@router.post("/retention/run", response_model=RetentionRunOut)
async def run_retention(body: RetentionRunIn, request: Request, principal: SettingsAdmin) -> RetentionRunOut:
    async with transaction(principal) as conn:
        result = await fetch_one(conn, "select public.run_retention_purge('manual') as counts")
        counts = dict(result["counts"]) if result else {}
        await record_event(principal, "privacy.retention_purged", "purge_log", None,
                           details={k: v for k, v in counts.items() if isinstance(v, int)}, conn=conn,
                           request_id=request.state.request_id)
    removed = 0
    try:  # separate transaction: a Storage failure keeps the paths queued for the next run
        async with transaction(principal) as conn:
            removed = await privacy.drain_storage_queue(conn)
    except privacy.StoragePurgeIncomplete:
        log.warning("storage_purge_incomplete")
    async with transaction(principal) as conn:
        pending = await _pending_files(conn)
    return RetentionRunOut(counts=counts, files_removed=removed, files_pending_removal=pending)


# ---------------------------------------------------------------------------
# Staff erasure requests (data-subject right to erasure)
# ---------------------------------------------------------------------------
@router.get("/privacy-requests", response_model=PrivacyRequestPage)
async def list_privacy_requests(principal: StaffAdmin,
                                status: Literal["pending", "completed", "rejected"] = "pending",
                                limit: Annotated[int, Query(ge=1, le=100)] = 50) -> PrivacyRequestPage:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """select r.id, r.user_id, sp.full_name, sp.email::text as email, r.kind, r.status,
               r.requested_at, r.decided_at
               from public.privacy_requests r join public.staff_profiles sp on sp.user_id = r.user_id
               where r.status = %s order by r.requested_at limit %s""", (status, limit))
    return PrivacyRequestPage(items=[PrivacyRequestOut(**r) for r in rows])


@router.post("/privacy-requests/{request_id}/complete", response_model=ErasureDecisionOut)
async def complete_erasure(request_id: UUID, body: ErasureCompleteIn, request: Request,
                           principal: StaffAdmin) -> ErasureDecisionOut:
    """Pseudonymise and deactivate the account; clinical records it authored are retained (health-record law)."""
    async with transaction(principal) as conn:
        row = await fetch_one(conn, """select r.user_id from public.privacy_requests r
               where r.id = %s and r.status = 'pending'""", (str(request_id),))
        if row is None:
            raise DomainError("Request not found.", 404)
        if row["user_id"] == principal.user_id:
            raise DomainError("Another administrator must complete your own erasure request.", 403)
        subject = await fetch_one(conn, "select public.complete_erasure_request(%s) as user_id", (str(request_id),))
        await record_event(principal, "privacy.erasure_completed", "privacy_request", str(request_id), conn=conn,
                           request_id=request.state.request_id)
    scrubbed = await privacy.scrub_auth_identity(UUID(str(subject["user_id"]))) if subject else False
    if not scrubbed:
        await record_event(principal, "privacy.identity_scrub_failed", "privacy_request", str(request_id),
                           outcome="failure", request_id=request.state.request_id)
    return ErasureDecisionOut(id=request_id, status="completed", identity_provider_scrubbed=scrubbed)


@router.post("/privacy-requests/{request_id}/reject", response_model=ErasureDecisionOut)
async def reject_erasure(request_id: UUID, request: Request, principal: StaffAdmin) -> ErasureDecisionOut:
    """Reject (e.g. duplicate or legally required retention); the requester sees the status in their export."""
    async with transaction(principal) as conn:
        row = await fetch_one(conn, """update public.privacy_requests
               set status = 'rejected', decided_by = %s, decided_at = now()
               where id = %s and status = 'pending' and user_id <> %s returning id""",
                              (str(principal.user_id), str(request_id), str(principal.user_id)))
        if row is None:
            raise DomainError("Request not found.", 404)
        await record_event(principal, "privacy.erasure_rejected", "privacy_request", str(request_id), conn=conn,
                           request_id=request.state.request_id)
    return ErasureDecisionOut(id=request_id, status="rejected")
