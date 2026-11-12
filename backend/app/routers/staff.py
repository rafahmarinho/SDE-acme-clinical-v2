"""API router: team management (administrators only).

New staff are invited through the Supabase Admin API (server-side service role key): Supabase
emails a one-time invitation link and the person sets their own password. No passwords are
generated, transmitted or stored by this API. Administrators cannot change their own role or
deactivate themselves (prevents lock-out and self-escalation).
"""

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.audit import record_event
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import StaffInvite, StaffOut, StaffUpdate

router = APIRouter(prefix="/v1/staff", tags=["staff"])
Admin = Annotated[Principal, Depends(require(Perm.STAFF_MANAGE))]

_SELECT = """select sp.user_id, sp.email::text as email, sp.full_name, sp.role::text as role, sp.is_active, sp.last_login_at,
                    coalesce(array_agg(a.ward_id) filter (where a.ward_id is not null), '{}') as ward_ids
             from public.staff_profiles sp left join public.staff_ward_assignments a on a.user_id = sp.user_id"""


@router.get("", response_model=list[StaffOut])
async def list_staff(principal: Admin) -> list[StaffOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, _SELECT + " group by sp.user_id order by sp.full_name")
    return [StaffOut(**r) for r in rows]


async def _invite_via_supabase(email: str, full_name: str) -> str:
    s = get_settings()
    key = s.supabase_service_role_key.get_secret_value()
    async with httpx.AsyncClient(base_url=str(s.supabase_url).rstrip("/"), timeout=10, verify=True) as client:
        resp = await client.post("/auth/v1/invite", json={"email": email, "data": {"full_name": full_name}},
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})
    if resp.status_code >= 400:
        # Same generic message whether or not the address already exists (no account enumeration).
        raise DomainError("The invitation could not be sent. Check the address and try again.", 400)
    return resp.json()["id"]


@router.post("", response_model=StaffOut, status_code=201)
async def invite_staff(body: StaffInvite, request: Request, principal: Admin) -> StaffOut:
    user_id = await _invite_via_supabase(str(body.email), body.full_name)
    async with transaction(principal) as conn:
        await conn.execute("insert into public.staff_profiles (user_id, email, full_name, role) values (%s, %s, %s, %s::public.app_role)",
                           (user_id, str(body.email).lower(), body.full_name, body.role.value))
        for ward in body.ward_ids:
            await conn.execute("insert into public.staff_ward_assignments (user_id, ward_id) values (%s, %s)", (user_id, str(ward)))
        await record_event(principal, "staff.invited", "staff_profile", user_id,
                           details={"role": body.role.value, "wards": len(body.ward_ids)}, conn=conn,
                           request_id=request.state.request_id)
        row = await fetch_one(conn, _SELECT + " where sp.user_id = %s group by sp.user_id", (user_id,))
    return StaffOut(**row)


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
        row = await fetch_one(conn, _SELECT + " where sp.user_id = %s group by sp.user_id", (str(user_id),))
    return StaffOut(**row)
