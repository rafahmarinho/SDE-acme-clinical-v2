"""API router: unified security settings (single administrator-managed interface)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.audit import record_event
from app.core.security import CurrentPrincipal, Perm, Principal, require
from app.db import fetch_one, transaction
from app.schemas import SecuritySettingsOut, SecuritySettingsUpdate

router = APIRouter(prefix="/v1/settings/security", tags=["settings"])

_COLUMNS = ("password_min_length", "session_idle_minutes", "session_absolute_hours", "max_concurrent_sessions",
            "lockout_threshold", "lockout_minutes", "require_mfa_for_admin", "data_retention_days")


@router.get("", response_model=SecuritySettingsOut)
async def get_security_settings(principal: CurrentPrincipal) -> SecuritySettingsOut:
    async with transaction(principal) as conn:
        row = await fetch_one(conn, "select * from public.security_settings where id = 1")
    return SecuritySettingsOut(**row)


@router.patch("", response_model=SecuritySettingsOut)
async def update_security_settings(body: SecuritySettingsUpdate, request: Request,
                                   principal: Annotated[Principal, Depends(require(Perm.SETTINGS_MANAGE))]) -> SecuritySettingsOut:
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
