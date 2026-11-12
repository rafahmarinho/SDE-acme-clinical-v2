"""API router: team management (administrators only, MFA enforced by get_principal).

Account lifecycle through Supabase Auth (the identity system of record):

* Invite: the Supabase Admin API (server-side service role key, TLS verified) e-mails a one-time
  invitation link and the person sets their own password. No passwords are generated, transmitted or
  stored by this API. The response is identical whether or not the address already belongs to a staff
  member (no account enumeration) and takes a uniform minimum time; duplicates are audit-logged so
  administrators can review them.
* Deactivate / reactivate: staff_profiles.is_active (checked on every API request) plus a Supabase Auth
  ban, so the person can no longer sign in or refresh a session anywhere.
* Unlock: clears the per-account soft lockout written by the Supabase password-verification hook.

Administrators cannot change their own role or deactivate themselves (prevents lock-out and
self-escalation). Every change is audit-logged. See docs/security/authentication.md.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from app.core.audit import record_event
from app.core.config import Settings, get_settings
from app.core.outbound import supabase_client
from app.core.errors import DomainError
from app.core.security import Perm, Principal, require, require_recent_auth
from app.db import fetch_all, fetch_one, transaction
from app.schemas import MAX_OFFSET, MAX_PAGE_SIZE, Page, RoleName, StaffInvite, StaffOut, StaffUpdate, Strict
from app.services.identity import canonical_email, uniform_auth_timing

router = APIRouter(prefix="/v1/staff", tags=["staff"])
Admin = Annotated[Principal, Depends(require(Perm.STAFF_MANAGE))]
# Account / privilege changes: permission + step-up re-authentication (recent password or MFA).
SteppedUpAdmin = Annotated[Principal, Depends(require_recent_auth(Perm.STAFF_MANAGE))]

INVITE_ACCEPTED = ("Invitation processed. If the address can receive invitations, the person will get an email "
                   "with a single-use link to set their password.")
BAN_FOREVER = "876000h"  # Supabase Auth ban duration used for deactivated accounts

_SELECT = """select sp.user_id, sp.email::text as email, sp.full_name, sp.role::text as role, sp.is_active, sp.last_login_at,
                    coalesce(array_agg(a.ward_id) filter (where a.ward_id is not null), '{}') as ward_ids
             from public.staff_profiles sp left join public.staff_ward_assignments a on a.user_id = sp.user_id"""


class InviteAccepted(BaseModel):
    detail: str


class RoleRequestIn(Strict):
    new_role: RoleName


class RoleRequestOut(BaseModel):
    id: UUID
    target_user_id: UUID
    new_role: RoleName
    requested_by: UUID
    requested_at: datetime
    status: Literal["pending", "approved", "rejected"]


ADMIN_PROMOTION_NEEDS_APPROVAL = ("Granting the administrator role needs a second administrator: create a role request "
                                  "and ask another administrator to approve it.")
# Revokes every app session of the target and deletes its Supabase Auth sessions/refresh tokens
# (supabase/migrations/0011_session_reset_on_privilege_change.sql).
REVOKE_SESSIONS_SQL = "select public.revoke_sessions_for_user(%s)"

_ROLE_REQUESTS_SQL ="""select id, target_user_id, new_role::text as new_role, requested_by, requested_at, status
                        from public.staff_role_requests where status = 'pending' order by requested_at desc limit %s"""
_ROLE_REQUEST_INSERT_SQL = """insert into public.staff_role_requests (target_user_id, new_role, requested_by)
                              values (%s, %s::public.app_role, %s)
                              returning id, target_user_id, new_role::text as new_role, requested_by, requested_at, status"""


def supabase_admin_client(settings: Settings) -> httpx.AsyncClient:
    """Outbound API -> Supabase Auth Admin: HTTPS with certificate verification, service key in headers only."""
    key = settings.supabase_service_role_key.get_secret_value()
    return supabase_client(10, settings, headers={"apikey": key, "Authorization": f"Bearer {key}"})


@router.get("", response_model=Page[StaffOut])
async def list_staff(principal: Admin, limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
                     offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0) -> Page[StaffOut]:
    async with transaction(principal, read_only=True) as conn:
        rows = await fetch_all(conn, _SELECT + " group by sp.user_id order by sp.full_name, sp.user_id limit %s offset %s",
                               (limit + 1, offset))
    return Page[StaffOut](items=[StaffOut(**r) for r in rows[:limit]],
                          next_offset=offset + limit if len(rows) > limit else None)


async def _invite_via_supabase(email: str, full_name: str) -> str | None:
    """Send the Supabase invitation; returns the new auth user id, or None if Supabase refused it."""
    s = get_settings()
    body: dict = {"email": email, "data": {"full_name": full_name}}
    if s.origins:
        body["redirect_to"] = f"{s.origins[0]}/reset-password"
    async with supabase_admin_client(s) as client:
        resp = await client.post("/auth/v1/invite", json=body)
    if resp.status_code >= 400:
        return None
    return str(resp.json()["id"])


async def _set_sign_in_ban(user_id: UUID, banned: bool) -> None:
    async with supabase_admin_client(get_settings()) as client:
        resp = await client.put(f"/auth/v1/admin/users/{user_id}", json={"ban_duration": BAN_FOREVER if banned else "none"})
    if resp.status_code >= 400:
        raise DomainError("The account could not be updated in the identity service. Try again.", 502)


@router.post("", response_model=InviteAccepted, status_code=202)
async def invite_staff(body: StaffInvite, request: Request, principal: SteppedUpAdmin) -> InviteAccepted:
    try:
        email = canonical_email(str(body.email))
    except ValueError as exc:
        raise DomainError(str(exc), 422) from exc
    async with uniform_auth_timing():
        async with transaction(principal) as conn:
            existing = await fetch_one(conn, "select user_id from public.staff_profiles where email = %s", (email,))
            if existing is not None:
                # Same response as a new invitation; administrators see the attempt in the audit log.
                await record_event(principal, "staff.invite_duplicate", "staff_profile", str(existing["user_id"]),
                                   outcome="denied", details={"role": body.role.value}, conn=conn,
                                   request_id=request.state.request_id)
                return InviteAccepted(detail=INVITE_ACCEPTED)
        user_id = await _invite_via_supabase(email, body.full_name)
        async with transaction(principal) as conn:
            if user_id is None:
                await record_event(principal, "staff.invite_failed", "staff_profile", None, outcome="failure",
                                   details={"role": body.role.value}, conn=conn, request_id=request.state.request_id)
                return InviteAccepted(detail=INVITE_ACCEPTED)
            await conn.execute("insert into public.staff_profiles (user_id, email, full_name, role) values (%s, %s, %s, %s::public.app_role)",
                               (user_id, email, body.full_name, body.role.value))
            for ward in body.ward_ids:
                await conn.execute("insert into public.staff_ward_assignments (user_id, ward_id) values (%s, %s)", (user_id, str(ward)))
            await record_event(principal, "staff.invited", "staff_profile", user_id,
                               details={"role": body.role.value, "wards": len(body.ward_ids)}, conn=conn,
                               request_id=request.state.request_id)
    return InviteAccepted(detail=INVITE_ACCEPTED)


@router.patch("/{user_id}", response_model=StaffOut)
async def update_staff(user_id: UUID, body: StaffUpdate, request: Request, principal: SteppedUpAdmin) -> StaffOut:
    if user_id == principal.user_id and (body.role is not None or body.is_active is False):
        raise DomainError("You cannot change your own role or deactivate your own account.", 403)
    async with transaction(principal) as conn:
        current = await fetch_one(conn, "select role::text as role, is_active from public.staff_profiles where user_id = %s for update",
                                  (str(user_id),))
        if current is None:
            raise HTTPException(404, "Staff member not found.")
        if body.role is RoleName.admin and current["role"] != RoleName.admin.value:
            # Two-person rule (also enforced by the staff_profiles_guard trigger): use a role request.
            raise DomainError(ADMIN_PROMOTION_NEEDS_APPROVAL, 409, code="approval_required")
        if body.role is not None:
            await conn.execute("update public.staff_profiles set role = %s::public.app_role where user_id = %s",
                               (body.role.value, str(user_id)))
        if body.is_active is not None:
            await conn.execute("update public.staff_profiles set is_active = %s, deactivated_at = case when %s then null else now() end "
                               "where user_id = %s", (body.is_active, body.is_active, str(user_id)))
        if body.ward_ids is not None:
            await conn.execute("delete from public.staff_ward_assignments where user_id = %s", (str(user_id),))
            for ward in body.ward_ids:
                await conn.execute("insert into public.staff_ward_assignments (user_id, ward_id) values (%s, %s)", (str(user_id), str(ward)))
        await record_event(principal, "staff.updated", "staff_profile", str(user_id),
                           details={"role": [current["role"], body.role.value if body.role else current["role"]],
                                    "is_active": body.is_active, "wards_changed": body.ward_ids is not None},
                           conn=conn, request_id=request.state.request_id)
        role_changed = body.role is not None and body.role.value != current["role"]
        if role_changed or body.is_active is False:
            # Privilege change: the user's existing sessions are revoked; they sign in again (T20).
            await conn.execute(REVOKE_SESSIONS_SQL, (str(user_id),))
        if body.is_active is not None and body.is_active != current["is_active"]:
            # Inside the transaction: if Supabase Auth cannot apply the ban, the deactivation is rolled back.
            await _set_sign_in_ban(user_id, banned=not body.is_active)
        row = await fetch_one(conn, _SELECT + " where sp.user_id = %s group by sp.user_id", (str(user_id),))
    return StaffOut(**row)


@router.post("/{user_id}/unlock", status_code=204)
async def unlock_staff(user_id: UUID, request: Request, principal: Admin) -> Response:
    """Clear a sign-in soft lockout (does not lift a deactivation ban)."""
    async with transaction(principal) as conn:
        row = await fetch_one(conn, "select public.unlock_staff_account(%s) as unlocked", (str(user_id),))
        await record_event(principal, "staff.unlocked", "staff_profile", str(user_id),
                           details={"was_locked": bool(row and row["unlocked"])}, conn=conn,
                           request_id=request.state.request_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Two-person rule for role changes (staff_role_requests, 0003_authz_rbac.sql): one administrator requests,
# a DIFFERENT administrator (never the target) approves, and the approval applies the role. The database
# trigger refuses an administrator promotion without such an approval; RLS/CHECKs forbid self-approval.
# ---------------------------------------------------------------------------
@router.get("/role-requests", response_model=Page[RoleRequestOut])
async def list_role_requests(principal: Admin,
                             limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE) -> Page[RoleRequestOut]:
    async with transaction(principal, read_only=True) as conn:
        rows = await fetch_all(conn, _ROLE_REQUESTS_SQL, (limit,))
    return Page[RoleRequestOut](items=[RoleRequestOut(**r) for r in rows])


@router.post("/{user_id}/role-requests", response_model=RoleRequestOut, status_code=201)
async def request_role_change(user_id: UUID, body: RoleRequestIn, request: Request,
                              principal: SteppedUpAdmin) -> RoleRequestOut:
    if user_id == principal.user_id:
        raise DomainError("You cannot request a role change for your own account.", 403)
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.staff_profiles where user_id = %s", (str(user_id),)) is None:
            raise HTTPException(404, "Staff member not found.")
        row = await fetch_one(conn, _ROLE_REQUEST_INSERT_SQL, (str(user_id), body.new_role.value, str(principal.user_id)))
        await record_event(principal, "staff.role_change_requested", "staff_profile", str(user_id),
                           details={"role_request_id": str(row["id"]), "new_role": body.new_role.value}, conn=conn,
                           request_id=request.state.request_id)
    return RoleRequestOut(**row)


@router.post("/role-requests/{role_request_id}/approve", response_model=StaffOut)
async def approve_role_change(role_request_id: UUID, request: Request, principal: SteppedUpAdmin) -> StaffOut:
    async with transaction(principal) as conn:
        req = await fetch_one(conn, """select target_user_id, new_role::text as new_role, requested_by, status
               from public.staff_role_requests where id = %s for update""", (str(role_request_id),))
        if req is None or req["status"] != "pending":
            raise HTTPException(404, "Pending role request not found.")
        if str(principal.user_id) in (str(req["requested_by"]), str(req["target_user_id"])):
            await record_event(principal, "staff.role_change_denied", "staff_role_request", str(role_request_id),
                               outcome="denied", conn=None, request_id=request.state.request_id)
            raise DomainError("A role change must be approved by a different administrator.", 403)
        target = str(req["target_user_id"])
        await conn.execute("""update public.staff_role_requests set status = 'approved', decided_by = %s, decided_at = now()
               where id = %s and status = 'pending'""", (str(principal.user_id), str(role_request_id)))
        await conn.execute("update public.staff_profiles set role = %s::public.app_role where user_id = %s",
                           (req["new_role"], target))
        await conn.execute(REVOKE_SESSIONS_SQL, (target,))  # sessions issued under the old role end now (T20)
        await record_event(principal, "staff.role_change_approved", "staff_profile", target,
                           details={"role_request_id": str(role_request_id), "new_role": req["new_role"],
                                    "requested_by": str(req["requested_by"])}, conn=conn,
                           request_id=request.state.request_id)
        row = await fetch_one(conn, _SELECT + " where sp.user_id = %s group by sp.user_id", (target,))
    return StaffOut(**row)



# ---------------------------------------------------------------------------
# Restriction of processing for secondary purposes (T754, public.processing_restrictions, 0013): the data stays
# stored, but staff activity reports, statistics and research extracts skip the person. Clinical care and the
# legally required audit trail cannot be restricted. Administrators only; both actions are audited.
# ---------------------------------------------------------------------------
RestrictableActivity = Literal["staff_activity_report", "statistics", "research_extract"]
RestrictionBasis = Literal["objection", "accuracy_contested", "unlawful_processing", "legal_claims"]


class RestrictionIn(Strict):
    activity: RestrictableActivity
    basis: RestrictionBasis


class RestrictionOut(BaseModel):
    id: UUID
    activity: RestrictableActivity
    basis: RestrictionBasis
    created_by: UUID
    created_at: datetime
    lifted_by: UUID | None = None
    lifted_at: datetime | None = None


_RESTRICTION_COLUMNS = "id, activity, basis, created_by, created_at, lifted_by, lifted_at"


@router.get("/{user_id}/processing-restrictions", response_model=Page[RestrictionOut])
async def list_restrictions(user_id: UUID, principal: Admin,
                            limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
                            offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0) -> Page[RestrictionOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, f"""select {_RESTRICTION_COLUMNS} from public.processing_restrictions
               where subject_type = 'staff' and subject_id = %s order by created_at desc limit %s offset %s""",
                               (str(user_id), limit + 1, offset))
    return Page[RestrictionOut](items=[RestrictionOut(**r) for r in rows[:limit]],
                                next_offset=offset + limit if len(rows) > limit else None)


@router.post("/{user_id}/processing-restrictions", response_model=RestrictionOut, status_code=201)
async def restrict_processing(user_id: UUID, body: RestrictionIn, request: Request, principal: Admin) -> RestrictionOut:
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.staff_profiles where user_id = %s", (str(user_id),)) is None:
            raise HTTPException(404, "Staff member not found.")
        row = await fetch_one(conn, f"""select {_RESTRICTION_COLUMNS} from public.processing_restrictions
               where subject_type = 'staff' and subject_id = %s and activity = %s and lifted_at is null""",
                              (str(user_id), body.activity))
        if row is None:
            row = await fetch_one(conn, f"""insert into public.processing_restrictions
                   (subject_type, subject_id, activity, basis, created_by) values ('staff', %s, %s, %s, %s)
                   returning {_RESTRICTION_COLUMNS}""", (str(user_id), body.activity, body.basis, str(principal.user_id)))
            await record_event(principal, "privacy.processing_restricted", "staff_profile", str(user_id),
                               details={"activity": body.activity, "basis": body.basis}, conn=conn,
                               request_id=request.state.request_id)
    return RestrictionOut(**row)


@router.delete("/{user_id}/processing-restrictions", status_code=204)
async def lift_restriction(user_id: UUID, activity: Annotated[RestrictableActivity, Query()], request: Request,
                           principal: Admin) -> Response:
    async with transaction(principal) as conn:
        row = await fetch_one(conn, """update public.processing_restrictions set lifted_at = now(), lifted_by = %s
               where subject_type = 'staff' and subject_id = %s and activity = %s and lifted_at is null returning id""",
                              (str(principal.user_id), str(user_id), activity))
        if row is None:
            raise HTTPException(404, "No active restriction for this activity.")
        await record_event(principal, "privacy.restriction_lifted", "staff_profile", str(user_id),
                           details={"activity": activity}, conn=conn, request_id=request.state.request_id)
    return Response(status_code=204)
