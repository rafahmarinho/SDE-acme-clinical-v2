"""API router: the caller's own personal data (skills/privacy).

* Review / update (T177/T238): GET and PATCH /v1/me. Only the name is editable here; the e-mail is the
  login identifier and changes through Supabase Auth's confirmed e-mail-change flow (mirrored into the
  profile by a trigger, 0007_privacy.sql); role, wards and activation are administrator-managed.
* Privacy notice before use (T239/T751/T752): GET /v1/me reports whether the CURRENT notice version
  was acknowledged; POST /v1/me/privacy-notice records the version with an evidence row. Profile
  changes are refused (409) until the current notice is acknowledged.
* Access / portability (T740/T741): POST /v1/me/export re-verifies the password and returns a complete,
  machine-readable JSON copy of the caller's data plus processing information, never other people's
  data; GET /v1/me/export is the same for a session authenticated within the step-up window.
* Erasure (T179/T240): POST /v1/me/erasure-request (password re-entry) creates a request that another
  administrator completes from the security settings screen; clinical records stay, pseudonymised.
Every action is audited with identifiers only.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, SecretStr, model_validator

from app.core.audit import record_event
from app.core.errors import DomainError
from app.core.security import CurrentPrincipal, Principal, require, require_recent_auth
from app.db import fetch_all, fetch_one, transaction
from app.schemas import Me, ProfileUpdate, Strict
from app.services import privacy

router = APIRouter(prefix="/v1/me", tags=["profile"])

# Authenticated self-service: any active staff member, no role permission (declared explicitly so the
# route inventory guard sees an authorization decision; see SELF_SERVICE_ROUTES in core/security.py).
SelfService = Annotated[Principal, Depends(require())]

NoticeVersion = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", max_length=10)]
Reauthentication = Annotated[SecretStr, Field(min_length=1, max_length=128,
                                              description="Your current password (re-authentication).")]


class MeOut(Me):
    privacy_notice_version: str | None = None
    privacy_notice_current_version: str = privacy.PRIVACY_NOTICE_VERSION
    privacy_notice_required: bool = True
    erasure_requested_at: datetime | None = None


class PrivacyNoticeAccept(Strict):
    notice_version: NoticeVersion


class ExportRequest(Strict):
    reauthentication: Reauthentication


class ErasureRequestIn(Strict):
    reauthentication: Reauthentication
    confirm_text: Annotated[str, Field(max_length=40)]

    @model_validator(mode="after")
    def _typed(self) -> "ErasureRequestIn":
        if self.confirm_text != "DELETE MY ACCOUNT":
            raise ValueError("type DELETE MY ACCOUNT to confirm")
        return self


class ErasureRequestOut(BaseModel):
    id: UUID
    status: Literal["pending", "completed", "rejected"]
    requested_at: datetime


class PersonalDataExport(BaseModel):
    format: Literal["acme-clinical-personal-data/v1"] = "acme-clinical-personal-data/v1"
    exported_at: datetime
    subject_id: UUID
    profile: dict[str, Any]
    ward_assignments: list[dict[str, Any]]
    privacy_notice_acknowledgements: list[dict[str, Any]]
    privacy_requests: list[dict[str, Any]]
    sessions: list[dict[str, Any]]
    observations_authored: list[dict[str, Any]]
    alarm_acknowledgements: list[dict[str, Any]]
    maintenance_performed: list[dict[str, Any]]
    files_uploaded: list[dict[str, Any]]
    emergency_access_grants: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]
    processing: dict[str, Any]


async def _load_me(conn, principal: Principal) -> MeOut:
    row = await fetch_one(conn, """
        select sp.user_id, sp.email::text as email, sp.full_name, sp.role::text as role, sp.previous_login_at,
               sp.privacy_notice_accepted_at, sp.privacy_notice_version, s.session_idle_minutes,
               coalesce(array_agg(a.ward_id) filter (where a.ward_id is not null), '{}') as ward_ids,
               (select max(r.requested_at) from public.privacy_requests r
                 where r.user_id = sp.user_id and r.status = 'pending') as erasure_requested_at
        from public.staff_profiles sp
        cross join public.security_settings s
        left join public.staff_ward_assignments a on a.user_id = sp.user_id
        where sp.user_id = %s
        group by sp.user_id, s.session_idle_minutes""", (str(principal.user_id),))
    if row is None:
        raise DomainError("Profile not found.", 404)
    return MeOut(**row, permissions=sorted(p.value for p in principal.permissions),
                 privacy_notice_required=privacy.notice_required(row.get("privacy_notice_version")))


@router.get("", response_model=MeOut)
async def get_me(principal: CurrentPrincipal) -> MeOut:
    async with transaction(principal) as conn:
        return await _load_me(conn, principal)


@router.patch("", response_model=MeOut)
async def update_me(body: ProfileUpdate, request: Request, principal: CurrentPrincipal) -> MeOut:
    async with transaction(principal) as conn:
        current = await _load_me(conn, principal)
        if current.privacy_notice_required:
            raise DomainError("Please read and acknowledge the privacy notice before updating your profile.", 409,
                              code="privacy_notice_required")
        await conn.execute("update public.staff_profiles set full_name = %s where user_id = %s",
                           (body.full_name, str(principal.user_id)))
        await record_event(principal, "profile.updated", "staff_profile", str(principal.user_id),
                           details={"fields": ["full_name"]}, conn=conn, request_id=request.state.request_id)
        return await _load_me(conn, principal)


@router.post("/privacy-notice", status_code=204)
async def accept_privacy_notice(request: Request, principal: CurrentPrincipal,
                                body: PrivacyNoticeAccept | None = None) -> None:
    version = body.notice_version if body else privacy.PRIVACY_NOTICE_VERSION
    if version != privacy.PRIVACY_NOTICE_VERSION:
        raise DomainError("The privacy notice has changed. Please reload and read the current version.", 409,
                          code="privacy_notice_outdated")
    async with transaction(principal) as conn:
        await conn.execute("""update public.staff_profiles set privacy_notice_accepted_at = now(),
                              privacy_notice_version = %s where user_id = %s""", (version, str(principal.user_id)))
        await conn.execute("""insert into public.privacy_consents (user_id, notice_version) values (%s, %s)
                              on conflict (user_id, notice_version) do nothing""", (str(principal.user_id), version))
        await record_event(principal, "privacy.notice_accepted", "staff_profile", str(principal.user_id),
                           details={"notice_version": version}, conn=conn, request_id=request.state.request_id)


async def _reverify(principal: Principal, secret: SecretStr, request: Request, purpose: str) -> None:
    if not await privacy.verify_password(principal.email, secret.get_secret_value()):
        await record_event(principal, "privacy.reauth_failed", "staff_profile", str(principal.user_id),
                           outcome="denied", details={"purpose": purpose}, request_id=request.state.request_id)
        # 400, not 401: the SPA treats 401 as "session ended" and signs the user out.
        raise DomainError("The password is incorrect.", 400, code="reauthentication_failed")


async def _build_export(conn, principal: Principal) -> PersonalDataExport:
    uid = (str(principal.user_id),)
    profile = await fetch_one(conn, """select user_id, email::text as email, full_name, role::text as role, is_active,
           last_login_at, previous_login_at, host(previous_login_ip) as previous_login_ip,
           privacy_notice_accepted_at, privacy_notice_version, created_at, updated_at, deactivated_at
           from public.staff_profiles where user_id = %s""", uid)
    wards = await fetch_all(conn, """select w.id as ward_id, w.code, w.name from public.staff_ward_assignments a
           join public.wards w on w.id = a.ward_id where a.user_id = %s order by w.code""", uid)
    consents = await fetch_all(conn, """select notice_version, accepted_at from public.privacy_consents
           where user_id = %s order by accepted_at""", uid)
    requests = await fetch_all(conn, """select id, kind, status, requested_at, decided_at from public.privacy_requests
           where user_id = %s order by requested_at""", uid)
    sessions = await fetch_all(conn, """select created_at, last_activity_at, revoked_at, revoked_reason
           from public.app_sessions where user_id = %s order by created_at desc limit 100""", uid)
    # Clinical content belongs to the patient record: listed by reference, without text or patient identity,
    # including records of patients the caller can no longer see (security-definer lookup, 0007_privacy.sql).
    refs = await fetch_all(conn, """select kind, record_id, recorded_at from public.my_authored_record_refs()
           order by recorded_at desc nulls last limit 5000""")
    grants = await fetch_all(conn, """select id, granted_at, expires_at, revoked_at, reviewed_at
           from public.break_glass_grants where user_id = %s order by granted_at desc limit 500""", uid)
    events = await fetch_all(conn, """select occurred_at, action, entity_type, outcome from public.events
           where actor_id = %s order by id desc limit 1000""", uid)

    def of(kind: str) -> list[dict[str, Any]]:
        return [{"id": r["record_id"], "at": r["recorded_at"]} for r in refs if r["kind"] == kind]

    return PersonalDataExport(
        exported_at=datetime.now(UTC), subject_id=principal.user_id, profile=profile or {}, ward_assignments=wards,
        privacy_notice_acknowledgements=consents, privacy_requests=requests, sessions=sessions,
        observations_authored=of("observation"), alarm_acknowledgements=of("alarm_acknowledgement"),
        maintenance_performed=of("maintenance"), files_uploaded=of("file_upload"), emergency_access_grants=grants,
        audit_events=events, processing={**privacy.PROCESSING_INFO, "retention_days": await _retention_days(conn)})


async def _retention_days(conn) -> int | None:
    row = await fetch_one(conn, "select data_retention_days from public.security_settings where id = 1")
    return row["data_retention_days"] if row else None


def _attachment_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = 'attachment; filename="acme-clinical-my-data.json"'


async def _export(principal: Principal, request: Request, response: Response, method: str) -> PersonalDataExport:
    async with transaction(principal) as conn:
        export = await _build_export(conn, principal)
        await record_event(principal, "privacy.data_exported", "staff_profile", str(principal.user_id),
                           details={"method": method}, conn=conn, request_id=request.state.request_id)
    _attachment_headers(response)
    return export


@router.post("/export", response_model=PersonalDataExport)
async def export_my_data(body: ExportRequest, request: Request, response: Response,
                         principal: SelfService) -> PersonalDataExport:
    """Machine-readable copy of the caller's personal data (right of access / portability)."""
    await _reverify(principal, body.reauthentication, request, "export")
    return await _export(principal, request, response, "password")


@router.get("/export", response_model=PersonalDataExport)
async def export_my_data_recent_session(request: Request, response: Response,
                                        principal: Annotated[Principal, Depends(require_recent_auth())]) -> PersonalDataExport:
    """Same export for a session whose last sign-in is within the step-up window."""
    return await _export(principal, request, response, "recent_session")


@router.post("/erasure-request", response_model=ErasureRequestOut, status_code=202)
async def request_erasure(body: ErasureRequestIn, request: Request, principal: SelfService) -> ErasureRequestOut:
    await _reverify(principal, body.reauthentication, request, "erasure")
    async with transaction(principal) as conn:
        existing = await fetch_one(conn, """select id, status, requested_at from public.privacy_requests
               where user_id = %s and kind = 'erasure' and status = 'pending'""", (str(principal.user_id),))
        row = existing or await fetch_one(conn, """insert into public.privacy_requests (user_id, kind)
               values (%s, 'erasure') returning id, status, requested_at""", (str(principal.user_id),))
        if existing is None:
            await record_event(principal, "privacy.erasure_requested", "privacy_request", str(row["id"]),
                               conn=conn, request_id=request.state.request_id)
    return ErasureRequestOut(**row)
