"""Authorization tests: route inventory (deny by default), unauthenticated access, role x permission
matrix, least privilege / revocation, separation of duties, step-up for sensitive transactions,
IDOR (404 for out-of-scope objects), centralization, and the break-glass cycle.

No database is available: handlers that would reach the DB are exercised with monkeypatched
`transaction` / `fetch_*` helpers; RLS behaviour itself is covered statically in
test_database_policies.py.
"""

from __future__ import annotations

import ast
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import get_settings
from app.core.security import (CONFLICTING_PERMISSIONS, PERMISSIONS, PUBLIC_ROUTES, SELF_SERVICE_ROUTES, CurrentPrincipal,
                               Perm, Principal, Role, assert_routes_protected, require_recent_auth, role_may_call,
                               route_permissions,
                               route_requires_authentication, route_requires_step_up, unprotected_routes)
from app.main import app as main_app
from app.routers import break_glass
from tests.conftest import add_identity, make_token

APP_DIR = Path(__file__).resolve().parents[1] / "app"
DUMMY_ID = "00000000-0000-4000-8000-0000000000aa"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _routes() -> list[tuple[str, str, APIRoute]]:
    return [(m, r.path, r) for r in main_app.routes if isinstance(r, APIRoute) for m in sorted(r.methods)]


def _url(path: str) -> str:
    out = path
    while "{" in out:
        start, end = out.index("{"), out.index("}")
        out = out[:start] + DUMMY_ID + out[end + 1:]
    return out


def _fresh_token(uid: str, *, role: str, auth_age_s: int = 0) -> str:
    ts = int(time.time()) - auth_age_s
    return make_token(uid, aal="aal2" if role == "admin" else "aal1",
                      amr=[{"method": "password", "timestamp": ts}])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


PROTECTED = [(m, p) for m, p, _ in _routes() if (m, p) not in PUBLIC_ROUTES]
PERMISSIONED = [(m, p, route_permissions(r)) for m, p, r in _routes() if route_permissions(r) is not None]


# ---------------------------------------------------------------------------
# Route inventory: deny by default (T2141, T2142, T16, T373)
# ---------------------------------------------------------------------------
def test_route_inventory_has_no_unprotected_routes():
    assert unprotected_routes(main_app, production=False) == []


def test_every_non_public_route_depends_on_authentication():
    missing = [f"{m} {p}" for m, p, r in _routes() if (m, p) not in PUBLIC_ROUTES and not route_requires_authentication(r)]
    assert missing == []


def test_every_mutating_route_declares_a_permission_or_is_self_service():
    missing = [f"{m} {p}" for m, p, r in _routes()
               if m in MUTATING and (m, p) not in SELF_SERVICE_ROUTES | PUBLIC_ROUTES and route_permissions(r) is None]
    assert missing == []


def test_public_and_self_service_whitelists_are_small_and_exist():
    paths = {(m, p) for m, p, _ in _routes()}
    # Liveness + browser CSP violation reports (browsers send them without credentials; see csp_report.py).
    assert PUBLIC_ROUTES == frozenset({("GET", "/v1/health"), ("POST", "/v1/csp-report")})
    assert PUBLIC_ROUTES <= paths
    assert SELF_SERVICE_ROUTES <= paths, "stale whitelist entries must be removed"
    assert not any(p.startswith(("/v1/staff", "/v1/simulation/", "/v1/thresholds", "/v1/break-glass"))
                   for _, p in SELF_SERVICE_ROUTES)


def test_startup_guard_rejects_route_without_authentication():
    rogue = FastAPI()

    @rogue.post("/v1/debug/reset")
    async def _reset() -> dict:
        return {}

    with pytest.raises(RuntimeError, match="no authentication dependency"):
        assert_routes_protected(rogue)


def test_startup_guard_rejects_mutating_route_without_permission():
    rogue = FastAPI()

    @rogue.post("/v1/staff/{user_id}/promote")
    async def _promote(user_id: str, principal: CurrentPrincipal) -> dict:
        return {}

    with pytest.raises(RuntimeError, match="no permission dependency"):
        assert_routes_protected(rogue)


def test_production_app_has_no_docs_and_passes_guard(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        from app.main import create_app

        prod = create_app()
        assert unprotected_routes(prod, production=True) == []
        with TestClient(prod) as c:
            for path in ("/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"):
                assert c.get(path).status_code in (401, 404)
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Unauthenticated access (T84, T2276) and public parts (T2282, T373)
# ---------------------------------------------------------------------------
def _bad_headers() -> list[dict]:
    now = int(time.time())
    return [
        {},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer invalid"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        _auth(make_token(iat=now - 7200, exp_in=60)),                      # expired
        _auth(make_token(secret="another-key-that-is-long-enough-000000")),  # wrong signing key
        _auth(make_token(aud="anon")),                                      # wrong audience
    ]


@pytest.mark.parametrize("method,path", PROTECTED, ids=[f"{m} {p}" for m, p in PROTECTED])
def test_protected_route_requires_valid_credentials(client, identities, method, path):
    for i, headers in enumerate(_bad_headers()):
        # distinct client address per attempt so per-client rate limiting does not mask the 401
        headers = {**headers, "X-Vercel-Forwarded-For": f"203.0.113.{i + 1}"}
        r = client.request(method, _url(path), headers=headers, json={} if method in MUTATING else None)
        assert r.status_code == 401, (headers, r.status_code, r.text)
        assert "Authentication required" in r.text


def test_token_for_unknown_user_is_rejected(client, identities):
    assert client.get("/v1/patients", headers=_auth(make_token())).status_code == 401


@pytest.mark.parametrize("method,path", sorted(PUBLIC_ROUTES))
def test_public_route_reachable_without_auth(client, method, path):
    r = client.request(method, path)
    if path == "/v1/csp-report":
        assert r.status_code == 204 and r.content == b""  # nothing reflected
        return
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}  # liveness only: no version, DB or environment details


@pytest.mark.parametrize("alt", ["/V1/patients", "/v1/Patients", "/v1/patients/", "/v1/../v1/patients",
                                 "/v1/patients;x=1", "/api/v1/patients", "/v1/staff/", "/v1/simulation/reset/"])
def test_alternative_paths_do_not_bypass_authentication(client, alt):
    r = client.get(alt)
    assert r.status_code in (401, 404, 405)
    assert "items" not in r.text


# ---------------------------------------------------------------------------
# Role x permission matrix, server-side enforcement (T2274, T2142, T85, T15)
# ---------------------------------------------------------------------------
EXPECTED_PERMISSIONS = {
    Role.NURSE: {"patient:read", "observation:write", "alarm:read", "alarm:ack", "device:read", "file:write",
                 "break_glass:request"},
    Role.PHYSICIAN: {"patient:read", "observation:write", "alarm:read", "alarm:ack", "threshold:write", "device:read",
                     "report:read", "file:write", "break_glass:request"},
    Role.BIOMED_TECH: {"alarm:read", "device:read", "device:write", "maintenance:read", "maintenance:write"},
    # maintenance:read (view history) but never maintenance:write (cross-owner request F3).
    Role.ADMIN: {"patient:read", "alarm:read", "device:read", "device:write", "maintenance:read", "report:read", "staff:manage",
                 "settings:manage", "simulation:control", "events:read_all", "break_glass:review"},
}


def test_permission_matrix_is_exactly_the_reviewed_one():
    """Fails if any role's permissions are widened (or narrowed) without updating this expectation."""
    assert {r: {p.value for p in perms} for r, perms in PERMISSIONS.items()} == EXPECTED_PERMISSIONS
    assert set(PERMISSIONS) == set(Role)


DENIAL_CASES = [(m, p, role) for m, p, r in _routes() if route_permissions(r) is not None
                for role in Role if not role_may_call(r, role)]


def test_every_role_is_denied_somewhere_and_matrix_drives_routes():
    denied_roles = {role for _, _, role in DENIAL_CASES}
    assert denied_roles == set(Role)
    assert len(PERMISSIONED) >= 25


@pytest.mark.parametrize("method,path,role", DENIAL_CASES, ids=[f"{r.value} {m} {p}" for m, p, r in DENIAL_CASES])
def test_role_without_permission_gets_403(client, identities, method, path, role):
    uid = add_identity(identities, role.value)
    # Forged role hints in headers and body must not change the outcome.
    headers = {**_auth(_fresh_token(uid, role=role.value)), "X-Role": "admin", "X-User-Id": str(uuid.uuid4())}
    r = client.request(method, _url(path), headers=headers,
                       json={"role": "admin", "is_admin": True} if method in MUTATING else None)
    assert r.status_code == 403, r.text
    assert r.json()["error"] == "You do not have permission to perform this action."
    assert any(e[0] == "authz.denied" and e[3] == "denied" for e in identities["__events__"])


def test_administrative_functions_denied_to_clinical_and_technical_roles(client, identities):
    for role in ("nurse", "physician", "biomed_tech"):
        uid = add_identity(identities, role)
        h = _auth(_fresh_token(uid, role=role))
        assert client.post("/v1/simulation/reset", headers=h, json={"confirm": "RESET"}).status_code == 403
        assert client.patch(f"/v1/staff/{DUMMY_ID}", headers=h, json={"role": "admin"}).status_code == 403
        assert client.post("/v1/staff", headers=h, json={}).status_code == 403
        assert client.patch("/v1/settings/security", headers=h, json={}).status_code == 403


def test_method_tampering_is_not_accepted(client, identities):
    uid = add_identity(identities, "nurse")
    h = _auth(_fresh_token(uid, role="nurse"))
    assert client.delete("/v1/patients", headers=h).status_code == 405
    assert client.put("/v1/simulation/reset", headers=h, json={}).status_code == 405


# ---------------------------------------------------------------------------
# Least privilege: granted late, revoked immediately (T2274, T14)
# ---------------------------------------------------------------------------
def test_deactivation_takes_effect_on_next_request_with_unexpired_token(client, identities, monkeypatch):
    uid = add_identity(identities, "biomed_tech")
    token = _fresh_token(uid, role="biomed_tech")
    assert client.get("/v1/patients", headers=_auth(token)).status_code == 403  # authenticated, not permitted
    identities[uid]["is_active"] = False
    assert client.get("/v1/patients", headers=_auth(token)).status_code == 401


def test_role_change_takes_effect_on_next_request(client, identities):
    uid = add_identity(identities, "admin")
    token = _fresh_token(uid, role="admin")
    h = _auth(token)
    identities[uid]["role"] = "nurse"  # demoted while the token is still valid
    assert client.get("/v1/staff", headers=h).status_code == 403


def test_role_claims_in_token_are_ignored(client, identities):
    uid = add_identity(identities, "nurse")
    token = make_token(uid, role="service_role", app_metadata={"role": "admin"}, user_metadata={"role": "admin"},
                       amr=[{"method": "password", "timestamp": int(time.time())}])
    assert client.get("/v1/staff", headers=_auth(token)).status_code == 403


# ---------------------------------------------------------------------------
# Separation of duties (T2388, T2393)
# ---------------------------------------------------------------------------
def test_no_role_holds_conflicting_permissions():
    for role, perms in PERMISSIONS.items():
        for pair in CONFLICTING_PERMISSIONS:
            assert not pair <= perms, f"{role} holds conflicting {sorted(pair)}"


def test_administrators_do_not_act_clinically():
    admin = PERMISSIONS[Role.ADMIN]
    assert not admin & {Perm.ALARM_ACK, Perm.OBSERVATION_WRITE, Perm.THRESHOLD_WRITE, Perm.BREAK_GLASS,
                        Perm.FILE_WRITE, Perm.MAINTENANCE_WRITE}
    assert Perm.STAFF_MANAGE not in PERMISSIONS[Role.PHYSICIAN] | PERMISSIONS[Role.NURSE] | PERMISSIONS[Role.BIOMED_TECH]


def test_admin_cannot_change_alarm_limits_or_acknowledge(client, identities):
    uid = add_identity(identities, "admin")
    h = _auth(_fresh_token(uid, role="admin"))
    body = {"parameter": "spo2", "low_limit": 80, "high_limit": 100, "confirm": True}
    assert client.put(f"/v1/thresholds/wards/{DUMMY_ID}", headers=h, json=body).status_code == 403
    assert client.post(f"/v1/alarms/{DUMMY_ID}/acknowledge", headers=h, json={}).status_code == 403


# ---------------------------------------------------------------------------
# Step-up re-authentication for highly sensitive transactions (T9, T83)
# ---------------------------------------------------------------------------
@pytest.fixture
def step_up_client(identities):
    mini = FastAPI()

    @mini.post("/sensitive")
    async def _sensitive(principal: Annotated[Principal, Depends(require_recent_auth(Perm.STAFF_MANAGE))]) -> dict:
        return {"ok": True}

    from app.core.middleware import SecurityHeadersMiddleware

    mini.add_middleware(SecurityHeadersMiddleware)
    with TestClient(mini) as c:
        yield c


def test_step_up_rejects_stale_authentication(step_up_client, identities):
    uid = add_identity(identities, "admin")
    r = step_up_client.post("/sensitive", headers=_auth(_fresh_token(uid, role="admin", auth_age_s=30 * 60)))
    assert r.status_code == 401
    challenge = r.headers["WWW-Authenticate"]
    assert 'error="insufficient_user_authentication"' in challenge and "step_up_required" in challenge
    assert ("authz.step_up_required", "route", "/sensitive", "denied") in identities["__events__"]


def test_step_up_rejects_tokens_without_auth_time(step_up_client, identities):
    uid = add_identity(identities, "admin")
    assert step_up_client.post("/sensitive", headers=_auth(make_token(uid, aal="aal2"))).status_code == 401


def test_step_up_accepts_recent_authentication(step_up_client, identities):
    uid = add_identity(identities, "admin")
    old = int(time.time()) - 3 * 3600
    token = make_token(uid, aal="aal2", amr=[{"method": "password", "timestamp": old},
                                             {"method": "totp", "timestamp": int(time.time()) - 30}])
    assert step_up_client.post("/sensitive", headers=_auth(token)).status_code == 200


def test_step_up_still_checks_permission_and_revocation(step_up_client, identities):
    nurse = add_identity(identities, "nurse")
    assert step_up_client.post("/sensitive", headers=_auth(_fresh_token(nurse, role="nurse"))).status_code == 403
    admin = add_identity(identities, "admin", active=False)  # suspended account, valid JWT
    assert step_up_client.post("/sensitive", headers=_auth(_fresh_token(admin, role="admin"))).status_code == 401


def test_break_glass_activation_requires_step_up():
    route = next(r for m, p, r in _routes() if (m, p) == ("POST", "/v1/break-glass"))
    assert route_requires_step_up(route)


# ---------------------------------------------------------------------------
# Centralized authorization (T15, T226)
# ---------------------------------------------------------------------------
def _role_comparisons(path: Path) -> list[str]:
    offenders = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            attrs = {n.attr for o in operands for n in ast.walk(o) if isinstance(n, ast.Attribute)}
            # A role decision = a role/is_admin attribute compared with a role literal or a Role member.
            role_values = [o for o in operands
                           if (isinstance(o, ast.Constant) and isinstance(o.value, str))
                           or (isinstance(o, ast.Attribute) and isinstance(o.value, ast.Name) and o.value.id == "Role")
                           or isinstance(o, (ast.Tuple, ast.Set, ast.List))]
            if attrs & {"role", "is_admin"} and role_values:
                offenders.append(f"{path.name}:{node.lineno}")
    return offenders


def test_no_role_comparisons_outside_security_module():
    offenders = []
    for path in list((APP_DIR / "routers").rglob("*.py")) + list((APP_DIR / "services").rglob("*.py")):
        offenders += _role_comparisons(path)
    assert offenders == [], offenders


def test_routers_do_not_compare_role_literals_in_sql():
    offenders = [p.name for p in (APP_DIR / "routers").rglob("*.py")
                 if "current_staff_role() =" in p.read_text(encoding="utf-8")
                 or "current_staff_role() in" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_routers_import_authorization_only_from_security_module():
    for path in (APP_DIR / "routers").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "def require(" not in text and "PERMISSIONS" not in text, path.name


# ---------------------------------------------------------------------------
# IDOR / user-controlled keys (T128, T106)
# ---------------------------------------------------------------------------
def test_object_keys_are_uuid_path_parameters():
    for _, path, route in _routes():
        for param in route.dependant.path_params:
            assert param.field_info.annotation is uuid.UUID, f"{path}: {param.name} must be a UUID"


class _FakeConn:
    async def execute(self, *a, **k):
        return None


def _fake_db(monkeypatch, module, rows: dict[str, object]):
    """Patch a router module's DB helpers: fetch_one returns rows[<first matching key in SQL>]."""
    calls: list[tuple[str, tuple]] = []

    @asynccontextmanager
    async def fake_tx(principal):
        yield _FakeConn()

    async def fake_one(conn, sql, params=()):
        calls.append((sql, params))
        for key, value in rows.items():
            if key in sql:
                return value(params) if callable(value) else value
        return None

    async def fake_all(conn, sql, params=()):
        calls.append((sql, params))
        return []

    monkeypatch.setattr(module, "transaction", fake_tx)
    monkeypatch.setattr(module, "fetch_one", fake_one)
    if hasattr(module, "fetch_all"):
        monkeypatch.setattr(module, "fetch_all", fake_all)
    return calls


def test_patient_outside_scope_is_indistinguishable_from_missing(client, identities, monkeypatch):
    from app.routers import patients

    _fake_db(monkeypatch, patients, {})  # RLS hides the other ward's patient: zero rows
    uid = add_identity(identities, "nurse")
    h = _auth(_fresh_token(uid, role="nurse"))
    other_ward = client.get(f"/v1/patients/{uuid.uuid4()}", headers=h)
    missing = client.get(f"/v1/patients/{uuid.uuid4()}/readings", headers=h)
    assert other_ward.status_code == missing.status_code == 404
    assert other_ward.json()["error"] == missing.json()["error"] == "Patient not found."


@pytest.mark.parametrize("bad", ["..%2f..%2fetc%2fpasswd", "ward-b%2Freport.pdf", "1", "PT-0007"])
def test_non_uuid_object_keys_rejected(client, identities, bad):
    uid = add_identity(identities, "physician")
    h = _auth(_fresh_token(uid, role="physician"))
    assert client.get(f"/v1/files/{bad}/url", headers=h).status_code in (404, 422)
    assert client.get(f"/v1/patients/{bad}", headers=h).status_code in (404, 422)


# ---------------------------------------------------------------------------
# Break glass (T337, T381)
# ---------------------------------------------------------------------------
@pytest.fixture
def bg(monkeypatch):
    events: list[tuple] = []

    async def fake_record(principal, action, entity_type, entity_id=None, **kw):
        events.append((action, entity_type, entity_id, kw.get("outcome", "success"), kw.get("details") or {}))

    monkeypatch.setattr(break_glass, "record_event", fake_record)
    return events


def _grant_row(params):
    from datetime import UTC, datetime

    return {"id": uuid.UUID(DUMMY_ID), "patient_id": uuid.UUID(params[1]), "expires_at": params[3]
            if isinstance(params[3], datetime) else datetime.now(UTC)}


def test_break_glass_requires_acknowledged_warning_and_reason(client, identities, bg, monkeypatch):
    _fake_db(monkeypatch, break_glass, {"patient_exists": {"ok": True}, "insert into": _grant_row})
    uid = add_identity(identities, "nurse")
    h = _auth(_fresh_token(uid, role="nurse"))
    pid = str(uuid.uuid4())
    assert client.post("/v1/break-glass", headers=h, json={"patient_id": pid, "reason": "Code blue, bed 4"}).status_code == 422
    assert client.post("/v1/break-glass", headers=h, json={"patient_id": pid, "reason": "short",
                                                           "acknowledged_warning": True}).status_code == 422
    assert client.post("/v1/break-glass", headers=h, json={"patient_id": pid, "reason": "Code blue, bed 4",
                                                           "acknowledged_warning": False}).status_code == 422
    # Mass assignment: the caller cannot choose the grantee or the expiry.
    assert client.post("/v1/break-glass", headers=h, json={"patient_id": pid, "reason": "Code blue, bed 4",
                                                           "acknowledged_warning": True, "user_id": str(uuid.uuid4()),
                                                           "expires_at": "2099-01-01T00:00:00Z"}).status_code == 422


def test_break_glass_full_activation_is_time_boxed_and_audited(client, identities, bg, monkeypatch):
    calls = _fake_db(monkeypatch, break_glass, {"patient_exists": {"ok": True}, "insert into": _grant_row})
    uid = add_identity(identities, "nurse")
    pid = str(uuid.uuid4())
    reason = "Code blue in ward B, covering nurse"
    before = time.time()
    r = client.post("/v1/break-glass", headers=_auth(_fresh_token(uid, role="nurse")),
                    json={"patient_id": pid, "reason": reason, "acknowledged_warning": True})
    assert r.status_code == 201, r.text
    insert = next(params for sql, params in calls if "insert into" in sql)
    assert insert[0] == uid and insert[1] == pid and insert[2] == reason  # grantee from the token, not the body
    ttl = insert[3].timestamp() - before
    assert 29 * 60 <= ttl <= 31 * 60
    action, entity, entity_id, outcome, details = bg[-1]
    assert (action, entity, entity_id, outcome) == ("break_glass.granted", "patient", pid, "success")
    assert details["grant_id"] == DUMMY_ID and details["minutes"] == 30 and details["warning_acknowledged"] is True
    assert reason not in str(details)  # free text stays on the grant row, not in audit details


def test_break_glass_stale_session_must_reauthenticate(client, identities, bg, monkeypatch):
    _fake_db(monkeypatch, break_glass, {"patient_exists": {"ok": True}, "insert into": _grant_row})
    uid = add_identity(identities, "physician")
    r = client.post("/v1/break-glass", headers=_auth(_fresh_token(uid, role="physician", auth_age_s=20 * 60)),
                    json={"patient_id": str(uuid.uuid4()), "reason": "Code blue, bed 4", "acknowledged_warning": True})
    assert r.status_code == 401 and "step_up_required" in r.headers["WWW-Authenticate"]


def test_break_glass_unknown_patient_is_404(client, identities, bg, monkeypatch):
    _fake_db(monkeypatch, break_glass, {"patient_exists": {"ok": False}})
    uid = add_identity(identities, "nurse")
    r = client.post("/v1/break-glass", headers=_auth(_fresh_token(uid, role="nurse")),
                    json={"patient_id": str(uuid.uuid4()), "reason": "Code blue, bed 4", "acknowledged_warning": True})
    assert r.status_code == 404


@pytest.mark.parametrize("role", ["admin", "biomed_tech"])
def test_break_glass_not_available_to_non_clinical_roles(client, identities, bg, role):
    uid = add_identity(identities, role)
    r = client.post("/v1/break-glass", headers=_auth(_fresh_token(uid, role=role)),
                    json={"patient_id": str(uuid.uuid4()), "reason": "Code blue, bed 4", "acknowledged_warning": True})
    assert r.status_code == 403


def test_break_glass_review_by_requester_is_forbidden(client, identities, bg, monkeypatch):
    uid = add_identity(identities, "admin")
    _fake_db(monkeypatch, break_glass, {"select user_id": {"user_id": uuid.UUID(uid), "reviewed_at": None}})
    r = client.post(f"/v1/break-glass/{DUMMY_ID}/review", headers=_auth(_fresh_token(uid, role="admin")),
                    json={"outcome": "appropriate"})
    assert r.status_code == 403
    assert bg[-1][0] == "break_glass.review_denied" and bg[-1][3] == "denied"


def test_break_glass_review_by_another_admin_records_outcome(client, identities, bg, monkeypatch):
    requester = str(uuid.uuid4())
    calls = _fake_db(monkeypatch, break_glass, {"select user_id": {"user_id": uuid.UUID(requester), "reviewed_at": None},
                                                "update public.break_glass_grants": {"id": uuid.UUID(DUMMY_ID)}})
    reviewer = add_identity(identities, "admin")
    h = _auth(_fresh_token(reviewer, role="admin"))
    assert client.post(f"/v1/break-glass/{DUMMY_ID}/review", headers=h, json={}).status_code == 422
    r = client.post(f"/v1/break-glass/{DUMMY_ID}/review", headers=h, json={"outcome": "inappropriate"})
    assert r.status_code == 204
    update = next(params for sql, params in calls if sql.lstrip().startswith("update"))
    assert update == (reviewer, "inappropriate", DUMMY_ID)
    assert bg[-1][:2] == ("break_glass.reviewed", "break_glass_grant") and bg[-1][4] == {"outcome": "inappropriate"}


def test_break_glass_review_twice_is_conflict_and_missing_is_404(client, identities, bg, monkeypatch):
    reviewer = add_identity(identities, "admin")
    h = _auth(_fresh_token(reviewer, role="admin"))
    _fake_db(monkeypatch, break_glass, {"select user_id": {"user_id": uuid.uuid4(), "reviewed_at": "2026-11-12"}})
    assert client.post(f"/v1/break-glass/{DUMMY_ID}/review", headers=h, json={"outcome": "appropriate"}).status_code == 409
    _fake_db(monkeypatch, break_glass, {})
    assert client.post(f"/v1/break-glass/{DUMMY_ID}/review", headers=h, json={"outcome": "appropriate"}).status_code == 404


def test_break_glass_early_revocation(client, identities, bg, monkeypatch):
    uid = add_identity(identities, "nurse")
    h = _auth(_fresh_token(uid, role="nurse"))
    _fake_db(monkeypatch, break_glass, {})  # not own / already ended: RLS returns no row
    assert client.post(f"/v1/break-glass/{DUMMY_ID}/revoke", headers=h).status_code == 404
    pid = uuid.uuid4()
    calls = _fake_db(monkeypatch, break_glass, {"update public.break_glass_grants": {"id": uuid.UUID(DUMMY_ID), "patient_id": pid}})
    assert client.post(f"/v1/break-glass/{DUMMY_ID}/revoke", headers=h).status_code == 204
    sql, params = calls[-1]
    assert "revoked_at is null and expires_at > now()" in sql and params == (uid, DUMMY_ID)
    assert bg[-1][0] == "break_glass.revoked"


@pytest.mark.asyncio
async def test_break_glass_use_is_audited_only_under_a_grant(monkeypatch, bg):
    principal = Principal(user_id=uuid.uuid4(), email="n@example.test", role=Role.NURSE, session_id=None, aal="aal1",
                          issued_at=0, auth_time=0, permissions=PERMISSIONS[Role.NURSE])
    _fake_db(monkeypatch, break_glass, {"active_break_glass_grant": {"grant_id": None}})
    await break_glass.record_break_glass_use(_FakeConn(), principal, uuid.uuid4(), "patient.read")
    assert bg == []
    _fake_db(monkeypatch, break_glass, {"active_break_glass_grant": {"grant_id": uuid.UUID(DUMMY_ID)}})
    await break_glass.record_break_glass_use(_FakeConn(), principal, uuid.uuid4(), "patient.read")
    assert bg[-1][0] == "break_glass.used" and bg[-1][4] == {"grant_id": DUMMY_ID, "action": "patient.read"}


def test_break_glass_scope_excludes_administrative_functions():
    assert not break_glass.BREAK_GLASS_SCOPE & {Perm.THRESHOLD_WRITE, Perm.STAFF_MANAGE, Perm.SIMULATION_CONTROL,
                                                Perm.DEVICE_WRITE, Perm.SETTINGS_MANAGE}
    assert break_glass.GRANT_DURATION.total_seconds() == 30 * 60
    assert security.STEP_UP_MAX_AGE.total_seconds() == 300


# ---------------------------------------------------------------------------
# Object-level authorization on every request (T378) and indirect file references (T50)
# ---------------------------------------------------------------------------
def test_t378_other_ward_alarm_and_attachment_are_404_like_missing(client, identities, monkeypatch):
    from app.routers import alarms, files

    alarm_calls = _fake_db(monkeypatch, alarms, {})  # RLS (can_access_patient) hides ward B's alarm: zero rows
    file_calls = _fake_db(monkeypatch, files, {})    # ... and ward B's attachment
    uid = add_identity(identities, "nurse")
    h = _auth(_fresh_token(uid, role="nurse"))
    r = client.post(f"/v1/alarms/{uuid.uuid4()}/acknowledge", headers=h, json={"acknowledged": True})
    assert r.status_code == 404 and r.json()["error"] == "Alarm not found."
    r = client.get(f"/v1/files/{uuid.uuid4()}/url", headers=h)
    assert r.status_code == 404 and r.json()["error"] == "File not found."
    # every lookup is keyed by the opaque id only; scoping is left to RLS under the caller's identity
    assert all("ward" not in sql.lower() for sql, _ in alarm_calls + file_calls)


@pytest.mark.parametrize("field", ["acknowledged_by", "user_id", "actor_id", "patient_id", "ward_id"])
def test_t378_client_supplied_owner_fields_are_rejected(client, identities, field):
    uid = add_identity(identities, "nurse")
    h = _auth(_fresh_token(uid, role="nurse"))
    r = client.post(f"/v1/alarms/{uuid.uuid4()}/acknowledge", headers=h, json={"acknowledged": True, field: str(uuid.uuid4())})
    assert r.status_code == 422


def test_t378_rls_scopes_reads_and_writes_of_clinical_objects():
    sql = "\n".join(p.read_text(encoding="utf-8") for p in sorted((APP_DIR.parents[1] / "supabase" / "migrations").glob("*.sql")))

    def last_policy(name: str) -> str:
        found = [s for s in sql.split(";") if f"create policy {name} " in s]
        assert found, name
        return found[-1]

    for name in ("patients_read", "alarms_read", "attachments_read", "observations_read"):
        assert "can_access_patient(" in last_policy(name), name
    update = last_policy("alarms_update")
    assert "can_access_patient(patient_id)" in update and "current_staff_role() is not null" not in update


def test_t50_object_paths_are_server_generated_uuids():
    from app.services import files as fs

    for bad in ("patients/../secrets", "patients/x/../../secrets.png", f"patients/{uuid.uuid4()}/report.pdf",
                "secrets", f"../{uuid.uuid4()}.png"):
        with pytest.raises(fs.FileRejected):
            fs.safe_object_path(bad)
    good = f"patients/{uuid.uuid4()}/{uuid.uuid4()}.png"
    assert fs.safe_object_path(good) == good
    for _, path, route in _routes():
        names = {p.name for p in route.dependant.path_params + route.dependant.query_params}
        assert not names & {"path", "file", "filename", "storage_path", "object_path"}, path


# ---------------------------------------------------------------------------
# Server-side authorization is the documented one (T17) and covers every role (T338)
# ---------------------------------------------------------------------------
def test_t17_documented_permission_table_matches_enforced_matrix():
    doc = (APP_DIR.parents[1] / "docs" / "security" / "authorization.md").read_text(encoding="utf-8")
    table = doc.split("| Permission | Nurse | Physician | Biomed tech | Admin |", 1)[1].split("\n\n", 1)[0]
    columns = [Role.NURSE, Role.PHYSICIAN, Role.BIOMED_TECH, Role.ADMIN]
    documented: dict[Role, set[str]] = {r: set() for r in columns}
    for line in table.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not cells[0].startswith("`"):
            continue
        for role, cell in zip(columns, cells[1:5]):
            if cell == "yes":
                documented[role].add(cells[0].strip("`"))
    assert documented == {r: {p.value for p in PERMISSIONS[r]} for r in columns}


def test_t17_forged_role_in_body_or_token_metadata_does_not_unlock_admin_routes(client, identities):
    uid = add_identity(identities, "nurse")
    token = make_token(uid, aal="aal2", auth_time=int(time.time()), app_metadata={"role": "admin"},
                       user_metadata={"role": "admin", "permissions": ["simulation:control"]})
    h = {**_auth(token), "X-Role": "admin"}
    forged = {"role": "admin", "permissions": ["settings:manage"], "acknowledged": True, "confirm_text": "RESET DEMO DATA"}
    assert client.post("/v1/simulation/reset", headers=h, json=forged).status_code == 403
    assert client.patch("/v1/settings/security", headers=h, json={"password_min_length": 12}).status_code == 403
    assert client.post("/v1/staff", headers=h, json={"email": "x@acme.test", "full_name": "X Y", "role": "admin"}).status_code == 403


def test_t338_unknown_role_gets_nothing(client, identities):
    uid = add_identity(identities, "nurse")
    identities[uid]["role"] = "auditor"  # a role absent from the permission table
    h = _auth(_fresh_token(uid, role="auditor"))
    for method, path in (("GET", "/v1/patients"), ("GET", "/v1/alarms"), ("GET", "/v1/monitors"), ("GET", "/v1/staff")):
        assert client.request(method, _url(path), headers=h).status_code in (401, 403), path


@pytest.mark.parametrize("method,path,body", [
    ("PATCH", "/v1/settings/security", {"password_min_length": 14}),
    ("POST", "/v1/simulation/reset", {"confirm_text": "RESET DEMO DATA", "acknowledged": True}),
])
def test_t338_stale_admin_login_needs_step_up_on_sensitive_admin_actions(client, identities, method, path, body):
    uid = add_identity(identities, "admin")
    stale = _fresh_token(uid, role="admin", auth_age_s=int(security.STEP_UP_MAX_AGE.total_seconds()) + 60)
    r = client.request(method, path, headers=_auth(stale), json=body)
    assert r.status_code == 401
    assert "step_up_required" in r.headers.get("WWW-Authenticate", "")
