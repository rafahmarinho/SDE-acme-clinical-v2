"""Authentication and authorization dependencies.

* Verifies Supabase-issued access tokens (HS256, audience, expiry, issuer) on every request.
* Resolves the caller's role from the server-side staff_profiles table, never from client input.
* Enforces a single, central permission matrix (nurse, physician, biomedical technician,
  administrator). Every non-public route declares the permission it needs via `require(...)`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings


class Role(StrEnum):
    NURSE = "nurse"
    PHYSICIAN = "physician"
    BIOMED_TECH = "biomed_tech"
    ADMIN = "admin"


class Perm(StrEnum):
    PATIENT_READ = "patient:read"
    OBSERVATION_WRITE = "observation:write"
    ALARM_READ = "alarm:read"
    ALARM_ACK = "alarm:ack"
    THRESHOLD_WRITE = "threshold:write"
    DEVICE_READ = "device:read"
    DEVICE_WRITE = "device:write"
    MAINTENANCE_WRITE = "maintenance:write"
    REPORT_READ = "report:read"
    FILE_WRITE = "file:write"
    BREAK_GLASS = "break_glass:request"
    BREAK_GLASS_REVIEW = "break_glass:review"
    STAFF_MANAGE = "staff:manage"
    SETTINGS_MANAGE = "settings:manage"
    SIMULATION_CONTROL = "simulation:control"
    EVENTS_READ_ALL = "events:read_all"


# Least privilege + separation of duties: administrators manage people, settings and the simulation,
# but do not author clinical observations or acknowledge alarms; clinicians cannot manage accounts.
PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.NURSE: frozenset({Perm.PATIENT_READ, Perm.OBSERVATION_WRITE, Perm.ALARM_READ, Perm.ALARM_ACK,
                          Perm.DEVICE_READ, Perm.FILE_WRITE, Perm.BREAK_GLASS}),
    Role.PHYSICIAN: frozenset({Perm.PATIENT_READ, Perm.OBSERVATION_WRITE, Perm.ALARM_READ, Perm.ALARM_ACK,
                              Perm.THRESHOLD_WRITE, Perm.DEVICE_READ, Perm.REPORT_READ, Perm.FILE_WRITE,
                              Perm.BREAK_GLASS}),
    Role.BIOMED_TECH: frozenset({Perm.ALARM_READ, Perm.DEVICE_READ, Perm.DEVICE_WRITE, Perm.MAINTENANCE_WRITE}),
    Role.ADMIN: frozenset({Perm.PATIENT_READ, Perm.ALARM_READ, Perm.DEVICE_READ, Perm.DEVICE_WRITE,
                          Perm.THRESHOLD_WRITE, Perm.REPORT_READ, Perm.STAFF_MANAGE, Perm.SETTINGS_MANAGE,
                          Perm.SIMULATION_CONTROL, Perm.EVENTS_READ_ALL, Perm.BREAK_GLASS_REVIEW}),
}


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    email: str
    role: Role
    session_id: str | None
    aal: str
    issued_at: int
    auth_time: int
    permissions: frozenset[Perm] = field(default_factory=frozenset)

    def can(self, perm: Perm) -> bool:
        return perm in self.permissions


_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required.",
    headers={"WWW-Authenticate": "Bearer"},
)
FORBIDDEN = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action.")


def decode_access_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            issuer=f"{str(settings.supabase_url).rstrip('/')}/auth/v1",
            options={"require": ["exp", "iat", "sub", "aud"]},
            leeway=10,
        )
    except jwt.PyJWTError as exc:  # never echo the reason to the client
        raise _UNAUTHORIZED from exc


async def get_principal(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise _UNAUTHORIZED
    claims = decode_access_token(creds.credentials, settings)
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise _UNAUTHORIZED from exc

    # Role/activation come from the database (authoritative), not from token claims the client could influence.
    from app.db import fetch_staff_identity  # local import avoids a cycle

    identity = await fetch_staff_identity(user_id)
    if identity is None or not identity["is_active"]:
        raise _UNAUTHORIZED

    sec = identity["security"]
    issued_at = int(claims["iat"])
    auth_time = int(claims.get("auth_time") or _first_amr_time(claims) or issued_at)
    now = int(time.time())
    if now - auth_time > int(sec["session_absolute_hours"]) * 3600:
        raise _UNAUTHORIZED  # absolute session timeout: user must sign in again

    role = Role(identity["role"])
    aal = str(claims.get("aal", "aal1"))
    if role is Role.ADMIN and sec["require_mfa_for_admin"] and aal != "aal2":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Multi-factor authentication is required.")

    principal = Principal(
        user_id=user_id,
        email=str(identity["email"]),
        role=role,
        session_id=claims.get("session_id"),
        aal=aal,
        issued_at=issued_at,
        auth_time=auth_time,
        permissions=PERMISSIONS[role],
    )
    request.state.principal = principal
    return principal


def _first_amr_time(claims: dict) -> int | None:
    amr = claims.get("amr")
    if isinstance(amr, list) and amr:
        ts = [int(e["timestamp"]) for e in amr if isinstance(e, dict) and "timestamp" in e]
        return min(ts) if ts else None
    return None


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require(*perms: Perm):
    """Route dependency: caller must hold every listed permission (deny by default)."""

    async def _check(request: Request, principal: CurrentPrincipal) -> Principal:
        missing = [p for p in perms if not principal.can(p)]
        if missing:
            from app.core.audit import record_event

            await record_event(principal, "authz.denied", "route", request.url.path,
                               outcome="denied", details={"permission": missing[0].value, "method": request.method})
            raise FORBIDDEN
        return principal

    return _check
