"""Authentication and authorization dependencies (the single, central authorization module).

* Verifies Supabase-issued access tokens (HS256, audience, expiry, issuer) on every request.
* Resolves the caller's role from the server-side staff_profiles table, never from client input
  (request bodies, headers such as X-Role, or user-editable token metadata are ignored).
* Enforces a single, central permission matrix (nurse, physician, biomedical technician,
  administrator). Every non-public route declares the permission it needs via `require(...)`.
* Holds the only whitelist of unauthenticated routes (`PUBLIC_ROUTES`) and of authenticated
  self-service routes that need no role permission (`SELF_SERVICE_ROUTES`); `assert_routes_protected`
  enforces both (deny by default) and is meant to run at application startup.
* Provides step-up re-authentication (`require_recent_auth`) for highly sensitive transactions and a
  single 404 helper so objects outside the caller's scope are indistinguishable from missing ones.

The permission matrix is mirrored in SQL (`public.role_permissions` / `public.has_permission()` in
supabase/migrations/0003_authz_rbac.sql); tests assert both definitions are identical.
See docs/security/authorization.md.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
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
    MAINTENANCE_READ = "maintenance:read"
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
# but do not author clinical observations, acknowledge alarms or change clinical alarm limits;
# clinicians cannot manage accounts; biomedical technicians have custody of devices only.
PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.NURSE: frozenset({Perm.PATIENT_READ, Perm.OBSERVATION_WRITE, Perm.ALARM_READ, Perm.ALARM_ACK,
                          Perm.DEVICE_READ, Perm.FILE_WRITE, Perm.BREAK_GLASS}),
    Role.PHYSICIAN: frozenset({Perm.PATIENT_READ, Perm.OBSERVATION_WRITE, Perm.ALARM_READ, Perm.ALARM_ACK,
                              Perm.THRESHOLD_WRITE, Perm.DEVICE_READ, Perm.REPORT_READ, Perm.FILE_WRITE,
                              Perm.BREAK_GLASS}),
    Role.BIOMED_TECH: frozenset({Perm.ALARM_READ, Perm.DEVICE_READ, Perm.DEVICE_WRITE, Perm.MAINTENANCE_READ,
                                Perm.MAINTENANCE_WRITE}),
    # Administrators may view maintenance history (fleet oversight) but never record maintenance.
    Role.ADMIN: frozenset({Perm.PATIENT_READ, Perm.ALARM_READ, Perm.DEVICE_READ, Perm.DEVICE_WRITE,
                          Perm.MAINTENANCE_READ, Perm.REPORT_READ, Perm.STAFF_MANAGE, Perm.SETTINGS_MANAGE,
                          Perm.SIMULATION_CONTROL, Perm.EVENTS_READ_ALL, Perm.BREAK_GLASS_REVIEW}),
}

# Static separation of duties: no role may ever hold both permissions of a pair (checked by tests).
CONFLICTING_PERMISSIONS: tuple[frozenset[Perm], ...] = (
    frozenset({Perm.STAFF_MANAGE, Perm.ALARM_ACK}),            # grant privileges vs act clinically
    frozenset({Perm.STAFF_MANAGE, Perm.OBSERVATION_WRITE}),
    frozenset({Perm.STAFF_MANAGE, Perm.THRESHOLD_WRITE}),      # grant privileges vs change alarm limits
    frozenset({Perm.STAFF_MANAGE, Perm.BREAK_GLASS}),          # grant privileges vs emergency access
    frozenset({Perm.BREAK_GLASS, Perm.BREAK_GLASS_REVIEW}),    # use emergency access vs review it
    frozenset({Perm.MAINTENANCE_WRITE, Perm.ALARM_ACK}),       # device custody vs clinical alarm handling
    frozenset({Perm.MAINTENANCE_WRITE, Perm.THRESHOLD_WRITE}),
)

# The ONLY routes reachable without authentication (reviewed whitelist; see docs/security/authorization.md).
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/v1/health"),  # liveness only: {"status": "ok"}, no version/DB/environment details
    # Browser CSP violation reports (no credentials possible): bounded body, allow-listed fields logged with
    # URLs reduced to their origin, always 204, rate-limited per IP. See app/routers/csp_report.py.
    ("POST", "/v1/csp-report"),
})
# FastAPI interactive docs: mounted only outside production (create_app sets docs_url/openapi_url=None).
NON_PRODUCTION_DOC_PATHS: frozenset[str] = frozenset({"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"})

# Authenticated routes every active staff member may use regardless of role (own profile/session,
# read-only views whose rows are scoped by RLS). Every other route must declare a permission.
SELF_SERVICE_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/v1/auth/session"),
    ("POST", "/v1/auth/logout"),
    ("GET", "/v1/me"),
    ("PATCH", "/v1/me"),
    ("POST", "/v1/me/privacy-notice"),
    ("GET", "/v1/me/export"),
    ("POST", "/v1/me/export"),
    ("POST", "/v1/me/erasure-request"),
    ("GET", "/v1/simulation"),
    ("GET", "/v1/events"),  # RLS: non-admins see only their own events
})

# Step-up window for highly sensitive transactions (staff role/activation changes, simulation reset,
# alarm-limit changes). Break-glass activation uses BREAK_GLASS_STEP_UP_MAX_AGE (see break_glass.py).
STEP_UP_MAX_AGE = timedelta(minutes=5)


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
    # Most recent primary authentication (password/OTP/MFA) from the token's `amr` claim; 0 if unknown.
    last_auth_at: int = 0

    def can(self, perm: Perm) -> bool:
        return perm in self.permissions

    def can_any(self, perms: Iterable[Perm]) -> bool:
        return any(p in self.permissions for p in perms)


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

    # Role/activation come from the database (authoritative) on EVERY request, so deactivation and
    # role changes take effect on the next call, without waiting for the token to expire.
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

    try:
        role = Role(identity["role"])
    except ValueError:  # a role outside the reviewed permission table gets nothing (fail closed, T338)
        raise _UNAUTHORIZED from None
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
        last_auth_at=_last_auth_time(claims),
    )
    # Server-side session state (revoked / idle / absolute timeout) on EVERY authenticated request.
    await _enforce_session(request, principal)
    request.state.principal = principal
    return principal


async def _enforce_session(request: Request, principal: Principal) -> None:
    """Indirection so unit tests without a database can stub the session check (see tests/conftest.py)."""
    from app.routers.auth import enforce_session  # local import avoids a cycle

    await enforce_session(request, principal)


def _amr_times(claims: dict) -> list[int]:
    amr = claims.get("amr")
    if isinstance(amr, list):
        return [int(e["timestamp"]) for e in amr if isinstance(e, dict) and "timestamp" in e]
    return []


def _first_amr_time(claims: dict) -> int | None:
    ts = _amr_times(claims)
    return min(ts) if ts else None


def _last_auth_time(claims: dict) -> int:
    """Latest authentication-method timestamp. Token refreshes do not change it; re-entering the password does."""
    ts = _amr_times(claims)
    if ts:
        return max(ts)
    return int(claims.get("auth_time") or 0)  # fail closed: unknown => step-up required


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


async def _deny(request: Request, principal: Principal, action: str, details: dict) -> None:
    from app.core.audit import record_event

    await record_event(principal, action, "route", request.url.path, outcome="denied",
                       details={**details, "method": request.method})


def require(*perms: Perm):
    """Route dependency: caller must hold every listed permission (deny by default)."""

    async def _check(request: Request, principal: CurrentPrincipal) -> Principal:
        missing = [p for p in perms if not principal.can(p)]
        if missing:
            await _deny(request, principal, "authz.denied", {"permission": missing[0].value})
            raise FORBIDDEN
        return principal

    _check.__perm__ = frozenset(perms)  # type: ignore[attr-defined]  # read by the route inventory guard
    return _check


def require_any(*perms: Perm):
    """Route dependency: caller must hold at least one of the listed permissions."""

    async def _check(request: Request, principal: CurrentPrincipal) -> Principal:
        if not principal.can_any(perms):
            await _deny(request, principal, "authz.denied", {"permission": perms[0].value})
            raise FORBIDDEN
        return principal

    _check.__perm__ = frozenset(perms)  # type: ignore[attr-defined]
    _check.__perm_any__ = True  # type: ignore[attr-defined]
    return _check


def step_up_required(max_age: timedelta = STEP_UP_MAX_AGE) -> HTTPException:
    challenge = ('Bearer error="insufficient_user_authentication", error_description="step_up_required", '
                 f'max_age="{int(max_age.total_seconds())}"')
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                         detail="Please confirm your identity again to continue.",
                         headers={"WWW-Authenticate": challenge})


def require_recent_auth(*perms: Perm, max_age: timedelta = STEP_UP_MAX_AGE):
    """Route dependency for highly sensitive transactions: permission check plus step-up re-authentication.

    The caller must hold every permission AND have authenticated (re-entered the password or completed
    MFA) within `max_age`. The SPA reacts to the 401 `step_up_required` challenge by asking for the
    password again (supabase.auth.signInWithPassword / reauthenticate) and retrying the request.
    Deactivated accounts are already refused by `get_principal` on every request.
    """
    base = require(*perms)

    # Default-value form: with postponed annotations, a closure variable inside Annotated[...] could not be
    # resolved by FastAPI, silently dropping the dependency.
    async def _check(request: Request, principal: Principal = Depends(base)) -> Principal:  # noqa: B008
        if int(time.time()) - principal.last_auth_at > max_age.total_seconds():
            await _deny(request, principal, "authz.step_up_required", {"max_age_s": int(max_age.total_seconds())})
            raise step_up_required(max_age)
        return principal

    _check.__perm__ = frozenset(perms)  # type: ignore[attr-defined]
    _check.__step_up__ = max_age  # type: ignore[attr-defined]
    return _check


def not_found(entity: str = "Resource") -> HTTPException:
    """Single response for "does not exist" and "exists but outside your scope" (no IDOR oracle)."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity} not found.")


def ensure_visible(row: dict | None, entity: str = "Resource") -> dict:
    """Return a row loaded under RLS, or raise the same 404 whether it is missing or out of scope."""
    if row is None:
        raise not_found(entity)
    return row


# ---------------------------------------------------------------------------
# Route inventory / deny-by-default guard
# ---------------------------------------------------------------------------
def _dependency_calls(dependant: Dependant) -> list:
    calls: list = []
    for dep in dependant.dependencies:
        calls.append(dep.call)
        calls.extend(_dependency_calls(dep))
    return calls


def route_permissions(route: APIRoute) -> frozenset[Perm] | None:
    """Permissions declared by a route's `require*()` dependency, or None if it declares none."""
    for call in _dependency_calls(route.dependant):
        perms = getattr(call, "__perm__", None)
        if perms is not None:
            return perms
    return None


def role_may_call(route: APIRoute, role: Role) -> bool:
    """Whether the central matrix lets `role` past the route's permission dependency."""
    granted = PERMISSIONS[role]
    for call in _dependency_calls(route.dependant):
        perms = getattr(call, "__perm__", None)
        if perms is not None:
            ok = bool(perms & granted) if getattr(call, "__perm_any__", False) else perms <= granted
            if not ok:
                return False
    return True


def route_requires_authentication(route: APIRoute) -> bool:
    return get_principal in _dependency_calls(route.dependant)


def route_requires_step_up(route: APIRoute) -> bool:
    return any(getattr(c, "__step_up__", None) is not None for c in _dependency_calls(route.dependant))


def unprotected_routes(app: FastAPI, *, production: bool = True) -> list[str]:
    """Policy violations: every route outside PUBLIC_ROUTES must authenticate, and every route outside
    SELF_SERVICE_ROUTES must declare an explicit permission."""
    problems: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            path = getattr(route, "path", repr(route))
            if production or path not in NON_PRODUCTION_DOC_PATHS:
                problems.append(f"{path}: non-API route not allowed")
            continue
        for method in sorted(route.methods):
            key = (method, route.path)
            if key in PUBLIC_ROUTES:
                continue
            if not route_requires_authentication(route):
                problems.append(f"{method} {route.path}: no authentication dependency")
            elif key not in SELF_SERVICE_ROUTES and route_permissions(route) is None:
                problems.append(f"{method} {route.path}: no permission dependency")
    return problems


def assert_routes_protected(app: FastAPI, *, production: bool = True) -> None:
    """Fail application startup if any route lacks authentication/authorization (deny by default)."""
    problems = unprotected_routes(app, production=production)
    if problems:
        raise RuntimeError("Unprotected routes: " + "; ".join(problems))
