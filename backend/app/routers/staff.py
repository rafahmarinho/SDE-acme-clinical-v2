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

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.audit import record_event
from app.core.config import Settings, get_settings
from app.core.errors import DomainError
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import StaffInvite, StaffOut, StaffUpdate
from app.services.identity import canonical_email, uniform_auth_timing

router = APIRouter(prefix="/v1/staff", tags=["staff"])
Admin = Annotated[Principal, Depends(require(Perm.STAFF_MANAGE))]

INVITE_ACCEPTED = ("Invitation processed. If the address can receive invitations, the person will get an email "
                   "with a single-use link to set their password.")
BAN_FOREVER = "876000h"  # Supabase Auth ban duration used for deactivated accounts

_SELECT = """select sp.user_id, sp.email::text as email, sp.full_name, sp.role::text as role, sp.is_active, sp.last_login_at,
                    coalesce(array_agg(a.ward_id) filter (where a.ward_id is not null), '{}') as ward_ids
             from public.staff_profiles sp left join public.staff_ward_assignments a on a.user_id = sp.user_id"""


class InviteAccepted(BaseModel):
    detail: str


def supabase_admin_client(settings: Settings) -> httpx.AsyncClient:
    """Outbound API -> Supabase Auth Admin: HTTPS with certificate verification, service key in headers only."""
    base = str(settings.supabase_url).rstrip("/")
    if settings.is_production and not base.startswith("https://"):
        raise RuntimeError("SUPABASE_URL must use https")
    key = settings.supabase_service_role_key.get_secret_value()
    return httpx.AsyncClient(base_url=base, timeout=10, verify=True, follow_redirects=False,
                             headers={"apikey": key, "Authorization": f"Bearer {key}"})


@router.get("", response_model=list[StaffOut])
async def list_staff(principal: Admin) -> list[StaffOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, _SELECT + " group by sp.user_id order by sp.full_name")
    return [StaffOut(**r) for r in rows]


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
async def invite_staff(body: StaffInvite, request: Request, principal: Admin) -> InviteAccepted:
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
async def update_staff(user_id: UUID, body: StaffUpdate, request: Request, principal: Admin) -> StaffOut:
    if user_id == principal.user_id and (body.role is not None or body.is_active is False):
        raise DomainError("You cannot change your own role or deactivate your own account.", 403)
    async with transaction(principal) as conn:
        current = await fetch_one(conn, "select role::text as role, is_active from public.staff_profiles where user_id = %s for update",
                                  (str(user_id),))
        if current is None:
            raise HTTPException(404, "Staff member not found.")
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
