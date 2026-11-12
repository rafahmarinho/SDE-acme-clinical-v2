"""API router: current user profile (review, update, export, privacy notice)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.core.audit import record_event
from app.core.security import CurrentPrincipal
from app.db import fetch_all, fetch_one, transaction
from app.schemas import Me, ProfileExport, ProfileUpdate

router = APIRouter(prefix="/v1/me", tags=["profile"])


async def _load_me(conn, principal) -> Me:
    row = await fetch_one(conn, """
        select sp.user_id, sp.email::text as email, sp.full_name, sp.role::text as role, sp.previous_login_at,
               sp.privacy_notice_accepted_at, s.session_idle_minutes,
               coalesce(array_agg(a.ward_id) filter (where a.ward_id is not null), '{}') as ward_ids
        from public.staff_profiles sp
        cross join public.security_settings s
        left join public.staff_ward_assignments a on a.user_id = sp.user_id
        where sp.user_id = %s
        group by sp.user_id, s.session_idle_minutes""", (str(principal.user_id),))
    assert row is not None
    return Me(**row, permissions=sorted(p.value for p in principal.permissions))


@router.get("", response_model=Me)
async def get_me(principal: CurrentPrincipal) -> Me:
    async with transaction(principal) as conn:
        return await _load_me(conn, principal)


@router.patch("", response_model=Me)
async def update_me(body: ProfileUpdate, request: Request, principal: CurrentPrincipal) -> Me:
    async with transaction(principal) as conn:
        await conn.execute("update public.staff_profiles set full_name = %s where user_id = %s",
                           (body.full_name, str(principal.user_id)))
        await record_event(principal, "profile.updated", "staff_profile", str(principal.user_id),
                           details={"fields": ["full_name"]}, conn=conn, request_id=request.state.request_id)
        return await _load_me(conn, principal)


@router.post("/privacy-notice", status_code=204)
async def accept_privacy_notice(request: Request, principal: CurrentPrincipal) -> None:
    async with transaction(principal) as conn:
        await conn.execute("update public.staff_profiles set privacy_notice_accepted_at = now() where user_id = %s",
                           (str(principal.user_id),))
        await record_event(principal, "privacy.notice_accepted", "staff_profile", str(principal.user_id),
                           conn=conn, request_id=request.state.request_id)


@router.get("/export", response_model=ProfileExport)
async def export_my_data(request: Request, principal: CurrentPrincipal) -> ProfileExport:
    """Machine-readable copy of the caller's personal data (right of access)."""
    async with transaction(principal) as conn:
        profile = await fetch_one(conn, """select user_id, email::text as email, full_name, role::text as role, is_active,
               last_login_at, previous_login_at, privacy_notice_accepted_at, created_at, updated_at
               from public.staff_profiles where user_id = %s""", (str(principal.user_id),))
        wards = await fetch_all(conn, "select ward_id from public.staff_ward_assignments where user_id = %s",
                                (str(principal.user_id),))
        authored = await fetch_one(conn, "select count(*)::int as n from public.observations where author_id = %s",
                                   (str(principal.user_id),))
        events = await fetch_all(conn, """select occurred_at, action, entity_type, outcome from public.events
               where actor_id = %s order by id desc limit 500""", (str(principal.user_id),))
        await record_event(principal, "privacy.data_exported", "staff_profile", str(principal.user_id),
                           conn=conn, request_id=request.state.request_id)
    return ProfileExport(profile=profile or {}, ward_ids=[w["ward_id"] for w in wards],
                         observations_authored=authored["n"] if authored else 0, events=events,
                         exported_at=datetime.now(UTC))
