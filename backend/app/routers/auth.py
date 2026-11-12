"""API router: auth session bookkeeping.

Login, logout, password recovery and MFA are performed by Supabase Auth from the browser
(email/password). After a successful sign-in the SPA calls POST /v1/auth/session so the API can
record the login, return the previous-login notice and audit the event. Logout is audited via
POST /v1/auth/logout after supabase.auth.signOut({ scope: 'local' }).
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.audit import record_event
from app.core.security import CurrentPrincipal
from app.db import fetch_one, transaction

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class SessionStart(BaseModel):
    previous_login_at: str | None
    previous_login_ip: str | None


@router.post("/session", response_model=SessionStart)
async def session_started(request: Request, principal: CurrentPrincipal) -> SessionStart:
    client_ip = (request.headers.get("x-vercel-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip() or None
    async with transaction(principal) as conn:
        prev = await fetch_one(conn, "select last_login_at, host(previous_login_ip) as ip from public.staff_profiles where user_id = %s",
                               (str(principal.user_id),))
        await conn.execute(
            """update public.staff_profiles
               set previous_login_at = last_login_at, previous_login_ip = %s::inet, last_login_at = now()
               where user_id = %s""", (client_ip, str(principal.user_id)))
        await record_event(principal, "auth.login", "session", principal.session_id,
                           details={"aal": principal.aal}, conn=conn, request_id=request.state.request_id)
    return SessionStart(previous_login_at=prev["last_login_at"].isoformat() if prev and prev["last_login_at"] else None,
                        previous_login_ip=prev["ip"] if prev else None)


@router.post("/logout", status_code=204)
async def logged_out(request: Request, principal: CurrentPrincipal) -> None:
    await record_event(principal, "auth.logout", "session", principal.session_id, request_id=request.state.request_id)
