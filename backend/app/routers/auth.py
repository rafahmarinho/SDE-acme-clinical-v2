"""API router: server-side session management on top of Supabase Auth.

Login, password recovery and MFA are performed by Supabase Auth in the browser (email/password).
Supabase issues the session: an access JWT carrying a random `session_id` claim plus a rotating
refresh token. The API adds the controls Supabase does not provide (see docs/security/sessions.md):

* ``POST /v1/auth/session`` - called right after every interactive sign-in, and then as the activity
  heartbeat (only on real user input, throttled by the SPA). The first call for a session registers it
  in ``public.app_sessions`` (keyed by the verified JWT ``session_id``, never by a client-supplied
  value), enforces the per-account concurrent-session limit (oldest sessions revoked first, refresh
  tokens deleted) and records the login. Later calls refresh the idle timer.
* ``POST /v1/auth/logout`` - revokes the session server-side (``auth.sessions`` row deleted, so the
  refresh token dies and RLS closes direct Supabase access), optionally every session of the user
  (``{"scope": "global"}``), and answers with ``Clear-Site-Data``.
* ``enforce_session`` - the idle / absolute / revocation check run for every authenticated request.

The API sets no cookies. ``set_secure_cookie`` is the only sanctioned way to add one in the future.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.core import audit
from app.core.config import get_settings
from app.core.middleware import client_ip
from app.core.security import CurrentPrincipal, Principal
from app.db import fetch_one, transaction

router = APIRouter(prefix="/v1/auth", tags=["auth"])

SESSION_ROUTE = ("POST", "/v1/auth/session")
LOGOUT_ROUTE = ("POST", "/v1/auth/logout")

# Sent on logout: wipes whatever the API origin may hold in the browser (HTTP cache, cookies, storage).
CLEAR_SITE_DATA = '"cache", "cookies", "storage"'

_MESSAGES = {
    "session_unknown": "Your session is not recognised. Please sign in again.",
    "session_revoked": "Your session was ended (signed out, or signed in on another device). Please sign in again.",
    "session_idle": "Your session timed out due to inactivity. Please sign in again.",
    "session_expired": "Your session has expired. Please sign in again.",
}


def _now() -> datetime:
    """Clock used by every timeout decision (patched in tests to simulate time)."""
    return datetime.now(UTC)


def session_error(code: str) -> HTTPException:
    """401 with a stable machine-readable reason in WWW-Authenticate (RFC 6750) and a generic message."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_MESSAGES[code],
        headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{code}"'},
    )


@dataclass(frozen=True)
class SessionVerdict:
    error: str | None = None          # session_* code when the request must be refused
    revoke_reason: str | None = None  # app_sessions.revoked_reason to record, if the session must be revoked now
    expires_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.error is None


def evaluate_session(state: dict | None, now: datetime) -> SessionVerdict:
    """Decide whether a registered session may be used at `now`.

    `state` is a row of public.session_state(): created_at, last_activity_at, revoked_at,
    auth_session_exists, idle_minutes, absolute_hours. The absolute lifetime is measured from the
    session start (created_at), so refreshing the JWT never extends it; the idle window is measured
    from the last real user activity (heartbeat), so background polling/Realtime never extends it.
    """
    if state is None:
        return SessionVerdict(error="session_unknown")
    if state["revoked_at"] is not None:
        return SessionVerdict(error="session_revoked")
    if not state["auth_session_exists"]:  # signed out at Supabase Auth (e.g. global sign-out)
        return SessionVerdict(error="session_revoked", revoke_reason="signed_out")
    expires_at = state["created_at"] + timedelta(hours=int(state["absolute_hours"]))
    if now >= expires_at:
        return SessionVerdict(error="session_expired", revoke_reason="absolute_timeout")
    if now - state["last_activity_at"] >= timedelta(minutes=int(state["idle_minutes"])):
        return SessionVerdict(error="session_idle", revoke_reason="idle_timeout")
    return SessionVerdict(expires_at=expires_at)


def _session_uuid(principal: Principal) -> UUID:
    try:
        return UUID(str(principal.session_id))
    except (TypeError, ValueError) as exc:  # tokens without a session_id claim are not accepted
        raise session_error("session_unknown") from exc


async def _check(conn, principal: Principal, sid: UUID) -> SessionVerdict:
    state = await fetch_one(conn, "select * from public.session_state(%s)", (str(sid),))
    verdict = evaluate_session(state, _now())
    if verdict.revoke_reason:
        await conn.execute("select public.revoke_session(%s, %s)", (str(sid), verdict.revoke_reason))
    return verdict


async def enforce_session(request: Request, principal: Principal) -> None:
    """Per-request session check (revoked / idle / absolute timeout), meant to run inside get_principal.

    Data requests do NOT count as activity. POST /v1/auth/session performs its own check because it is
    the call that registers a new session.
    """
    if (request.method, request.url.path) == SESSION_ROUTE:
        return
    sid = _session_uuid(principal)
    async with transaction(principal) as conn:
        verdict = await _check(conn, principal, sid)
    if not verdict.active:  # raised after commit so the revocation is persisted
        raise session_error(verdict.error or "session_unknown")


def _ip_or_none(request: Request) -> str | None:
    raw = client_ip(request)
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def _ip_hash(ip: str | None) -> str | None:
    if ip is None:
        return None
    key = get_settings().supabase_jwt_secret.get_secret_value().encode()
    return hmac.new(key, b"acme.session-ip|" + ip.encode(), hashlib.sha256).hexdigest()


class SessionStart(BaseModel):
    session_id: str
    new_session: bool
    previous_login_at: str | None
    previous_login_ip: str | None
    revoked_sessions: int
    previous_session_unclosed: bool
    expires_at: str | None


@router.post("/session", response_model=SessionStart)
async def session_started(request: Request, principal: CurrentPrincipal) -> SessionStart:
    sid = _session_uuid(principal)  # derived from the verified JWT only; request bodies are ignored
    ip = _ip_or_none(request)
    user_agent = (request.headers.get("user-agent") or "")[:256]
    prev = None
    async with transaction(principal) as conn:
        reg = await fetch_one(conn, "select * from public.register_session(%s, %s, %s)",
                              (str(sid), user_agent, _ip_hash(ip)))
        if reg is None or reg["status"] != "active":
            verdict = SessionVerdict(error="session_revoked")
        else:
            verdict = await _check(conn, principal, sid)
        if verdict.active:
            await conn.execute("select public.touch_session(%s)", (str(sid),))
            if reg["created"]:
                prev = await fetch_one(
                    conn,
                    "select last_login_at, host(last_login_ip) as ip from public.staff_profiles where user_id = %s",
                    (str(principal.user_id),))
                await conn.execute(
                    """update public.staff_profiles
                       set previous_login_at = last_login_at, previous_login_ip = last_login_ip,
                           last_login_at = now(), last_login_ip = %s::inet
                       where user_id = %s""", (ip, str(principal.user_id)))
                await audit.record_event(principal, "auth.login", "session", str(sid),
                                         details={"aal": principal.aal, "revoked_sessions": reg["revoked_count"]},
                                         conn=conn, request_id=request.state.request_id)
    if not verdict.active:
        raise session_error(verdict.error or "session_revoked")
    created = bool(reg["created"])
    return SessionStart(
        session_id=str(sid),
        new_session=created,
        previous_login_at=prev["last_login_at"].isoformat() if prev and prev["last_login_at"] else None,
        previous_login_ip=prev["ip"] if prev else None,
        revoked_sessions=int(reg["revoked_count"] or 0),
        previous_session_unclosed=bool(reg["previous_unclosed"]),
        expires_at=verdict.expires_at.isoformat() if verdict.expires_at else None,
    )


class LogoutIn(BaseModel):
    scope: Literal["local", "global"] = "local"


@router.post("/logout", status_code=204)
async def logged_out(request: Request, principal: CurrentPrincipal, body: LogoutIn | None = None) -> Response:
    scope = body.scope if body else "local"
    try:
        sid = str(UUID(str(principal.session_id)))
    except (TypeError, ValueError):
        sid = None
    async with transaction(principal) as conn:
        if scope == "global":
            await conn.execute("select public.revoke_user_sessions(%s)", ("logout_all",))
        elif sid is not None:
            await conn.execute("select public.revoke_session(%s, %s)", (sid, "logout"))
        await audit.record_event(principal, "auth.logout", "session", sid, details={"scope": scope},
                                 conn=conn, request_id=request.state.request_id)
    return Response(status_code=204, headers={"Clear-Site-Data": CLEAR_SITE_DATA, "Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Cookies: the API sets none (Bearer tokens only). Any future cookie MUST be created here.
# ---------------------------------------------------------------------------
COOKIE_MAX_PATH = "/v1/auth"


def set_secure_cookie(response: Response, name: str, value: str, *, path: str = COOKIE_MAX_PATH) -> None:
    """Set an opaque, host-only, non-persistent cookie with HttpOnly, Secure and SameSite=Strict.

    No Domain attribute (host-only), no Max-Age/Expires (dies with the browser), a ``__Host-`` or
    ``__Secure-`` name prefix so browsers enforce Secure, and a narrow path (``/`` only for ``__Host-``,
    which the prefix requires). Never put personal data, roles or JWTs in a cookie value.
    """
    if name.startswith("__Host-"):
        if path != "/":
            raise ValueError("__Host- cookies require path '/'")
    elif not name.startswith("__Secure-"):
        raise ValueError("cookie names must use the __Host- or __Secure- prefix")
    elif not (path == COOKIE_MAX_PATH or path.startswith(COOKIE_MAX_PATH + "/")):
        raise ValueError(f"cookie path must be within {COOKIE_MAX_PATH}")
    if value.count(".") == 2 and value.startswith("eyJ"):
        raise ValueError("JWTs must not be stored in cookies")
    response.set_cookie(name, value, httponly=True, secure=True, samesite="strict", path=path)
