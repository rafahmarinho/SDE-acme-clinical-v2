"""Integration tests for the cross-owner wiring done after the parallel hardening (cross-owner requests
A1-A5, S1, L1-L2, I3-I7, N2-N4, P1, P7-P8, W1-W3, F1, F3-F4). No database: ``fake_db`` records SQL."""

from __future__ import annotations

import logging
import time
import uuid

import pytest
from fastapi.routing import APIRoute

from app.core import security
from app.core.config import Settings
from app.core.middleware import RateLimitMiddleware
from app.core.security import PERMISSIONS, PUBLIC_ROUTES, SELF_SERVICE_ROUTES, Perm, Role
from app.main import create_app
from app.routers import auth as auth_router
from app.services import alarms as alarm_service
from app.services import device_auth, simulation
from tests.conftest import add_identity, make_token
from tests.test_input_validation import MID, PID, fake_db  # noqa: F401 - fixture re-export

REAL_ENFORCE_SESSION = security._enforce_session  # captured before conftest stubs it per test
NOW = "2026-11-12T08:00:00+00:00"


@pytest.fixture
def recorded(monkeypatch):
    """Audit records written by the routers (they import record_event by name)."""
    events: list[tuple] = []

    async def fake_record(principal, action, entity_type, entity_id=None, **kw):
        events.append((action, entity_type, entity_id, kw.get("outcome", "success")))

    import importlib

    for name in ("break_glass", "monitors", "staff", "patients", "observations", "alarms", "files"):
        module = importlib.import_module(f"app.routers.{name}")
        if hasattr(module, "record_event"):
            monkeypatch.setattr(module, "record_event", fake_record)
    return events


def hdr(identities, role: str, *, recent: bool = True, uid: str | None = None) -> dict[str, str]:
    uid = uid or add_identity(identities, role)
    auth_time = int(time.time()) - (0 if recent else 3600)
    token = make_token(uid, aal="aal2" if role == "admin" else "aal1", auth_time=auth_time)
    return {"Authorization": f"Bearer {token}"}


def routes(app=None) -> dict[tuple[str, str], APIRoute]:
    app = app or create_app()
    return {(m, r.path): r for r in app.routes if isinstance(r, APIRoute) for m in r.methods}


# --------------------------------------------------------------------------- S1 session enforcement
def test_s1_get_principal_runs_server_side_session_check(client, identities, monkeypatch):
    calls = []

    async def spy(request, principal):
        calls.append((request.url.path, principal.session_id))
        raise auth_router.session_error("session_idle")

    monkeypatch.setattr(security, "_enforce_session", REAL_ENFORCE_SESSION)
    monkeypatch.setattr(auth_router, "enforce_session", spy)
    r = client.get("/v1/me", headers=hdr(identities, "nurse"))
    assert r.status_code == 401 and "session_idle" in r.headers["www-authenticate"]
    assert calls and calls[0][0] == "/v1/me"


# --------------------------------------------------------------------------- P1 / W1 route whitelists
def test_p1_self_service_routes_exist_and_settings_is_not_self_service():
    table = routes()
    assert ("GET", "/v1/settings/security") not in SELF_SERVICE_ROUTES
    for key in (("POST", "/v1/me/export"), ("POST", "/v1/me/erasure-request")):
        assert key in SELF_SERVICE_ROUTES and key in table
    assert all(key in table for key in SELF_SERVICE_ROUTES)


def test_w1_public_routes_are_exactly_health_and_csp_report_and_guard_still_bites():
    assert PUBLIC_ROUTES == {("GET", "/v1/health"), ("POST", "/v1/csp-report")}
    app = create_app()
    assert security.unprotected_routes(app, production=True) == []

    @app.get("/v1/csp-report")  # same path, other method: not whitelisted
    async def _leak() -> dict:
        return {}

    assert any("GET /v1/csp-report" in p for p in security.unprotected_routes(app, production=True))


def test_w1_csp_report_accepts_reports_logs_origin_only_and_always_204(client, caplog):
    report = {"csp-report": {"document-uri": "https://acme-clinical.vercel.app/patients/PT-0001?q=Smith",
                             "blocked-uri": "https://evil.example/x.js?token=abc", "violated-directive": "script-src-elem",
                             "original-policy": "default-src 'self'", "script-sample": "alert('PT-0001')"}}
    with caplog.at_level(logging.WARNING, logger="acme.security.csp"):
        r = client.post("/v1/csp-report", content=__import__("json").dumps(report),
                        headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204 and r.content == b""
    rec = next(rec for rec in caplog.records if rec.getMessage() == "csp_violation")
    assert rec.csp == {"document": "https://acme-clinical.vercel.app", "blocked": "https://evil.example",
                       "directive": "script-src-elem"}
    logged = repr(rec.__dict__)
    assert "PT-0001" not in logged and "token=abc" not in logged and "Smith" not in logged
    # Reporting API format, junk and unknown media types: still 204, never an error oracle.
    api_fmt = [{"type": "csp-violation", "body": {"documentURL": "https://a.example/p", "effectiveDirective": "img-src"}}]
    assert client.post("/v1/csp-report", json=api_fmt).status_code == 204
    assert client.post("/v1/csp-report", content=b"{not json", headers={"Content-Type": "application/csp-report"}).status_code == 204
    assert client.post("/v1/csp-report", content=b"a=b", headers={"Content-Type": "text/plain"}).status_code == 204
    big = b'{"csp-report": {"blocked-uri": "' + b"a" * 9000 + b'"}}'
    assert client.post("/v1/csp-report", content=big, headers={"Content-Type": "application/csp-report"}).status_code == 204


def test_w1_csp_report_is_rate_limited_per_ip(client):
    codes = [client.post("/v1/csp-report", json={}).status_code for _ in range(25)]
    assert 429 in codes and codes[0] == 204


# --------------------------------------------------------------------------- W2 / W3 headers
@pytest.mark.parametrize("path,expected", [("/v1/health", 200), ("/v1/patients", 401), ("/v1/nope", 404)])
def test_w2_cache_headers_on_every_response(client, path, expected):
    r = client.get(path)
    assert r.status_code == expected
    assert r.headers["cache-control"] == "no-store, no-cache, max-age=0, must-revalidate, private"
    assert r.headers["pragma"] == "no-cache" and r.headers["expires"] == "0"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert int(r.headers["strict-transport-security"].split("max-age=")[1].split(";")[0]) >= 31536000
    assert "server" not in r.headers and "x-powered-by" not in r.headers
    assert r.headers["content-type"].startswith("application/json")


def test_w3_lookalike_origin_gets_no_cors_and_form_posts_are_refused(client, identities):
    r = client.get("/v1/health", headers={"Origin": "https://acme-clinical.vercel.app.evil.example"})
    assert "access-control-allow-origin" not in r.headers
    pre = client.options("/v1/patients", headers={"Origin": "https://acme-clinical.vercel.app",
                                                  "Access-Control-Request-Method": "GET"})
    assert "www-authenticate" in pre.headers.get("access-control-expose-headers", "").lower() or pre.status_code == 200
    h = hdr(identities, "nurse")
    r = client.post(f"/v1/patients/{PID}/observations", content=b"body=x", headers={**h, "Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415
    assert client.post(f"/v1/patients/{PID}/observations", json={"body": "x"}, cookies={"sb": "x"}).status_code == 401


def test_w3_cors_exposes_step_up_challenge_header(client):
    r = client.get("/v1/health", headers={"Origin": "https://acme-clinical.vercel.app"})
    exposed = r.headers.get("access-control-expose-headers", "").lower()
    assert "www-authenticate" in exposed and "x-request-id" in exposed


# --------------------------------------------------------------------------- P8 rate-limit key
def test_p8_rate_limit_key_never_uses_unverified_claims(client, identities):
    victim = add_identity(identities, "nurse")
    forged = make_token(victim, secret="attacker-controlled-secret-0123456789")
    real = make_token(victim)

    class Req:
        def __init__(self, token):
            self.headers = {"authorization": f"Bearer {token}"}

    assert RateLimitMiddleware._subject(Req(forged)) != RateLimitMiddleware._subject(Req(real))
    assert victim not in (RateLimitMiddleware._subject(Req(real)) or "")
    assert RateLimitMiddleware._subject(Req("")) is None


# --------------------------------------------------------------------------- A1 / A3 step-up
def test_a1_reset_uses_security_definer_function_only():
    assert simulation.RESET_SQL[0] == "select public.reset_simulation_data()"
    assert not any(s.lstrip().lower().startswith("delete") for s in simulation.RESET_SQL)


STEP_UP_ROUTES = [("POST", "/v1/staff"), ("PATCH", "/v1/staff/{user_id}"), ("POST", "/v1/simulation/reset"),
                  ("PUT", "/v1/thresholds/wards/{ward_id}"), ("PUT", "/v1/thresholds/patients/{patient_id}"),
                  ("POST", "/v1/staff/{user_id}/role-requests"), ("POST", "/v1/staff/role-requests/{role_request_id}/approve"),
                  ("POST", "/v1/break-glass")]


@pytest.mark.parametrize("key", STEP_UP_ROUTES)
def test_a3_sensitive_routes_require_step_up(key):
    assert security.route_requires_step_up(routes()[key])


def test_a3_stale_authentication_gets_step_up_challenge_with_code(client, identities, fake_db):
    h = hdr(identities, "admin", recent=False)
    r = client.post("/v1/simulation/reset", headers=h, json={"confirm_text": "RESET DEMO DATA", "acknowledged": True})
    assert r.status_code == 401
    assert "step_up_required" in r.headers["www-authenticate"] and r.json()["code"] == "step_up_required"
    r = client.patch(f"/v1/staff/{PID}", headers=h, json={"is_active": False})
    assert r.status_code == 401 and r.json()["code"] == "step_up_required"
    ph = hdr(identities, "physician", recent=False)
    body = {"parameter": "spo2", "low_limit": 90, "high_limit": 100, "confirm": True}
    assert client.put(f"/v1/thresholds/wards/{PID}", headers=ph, json=body).json()["code"] == "step_up_required"


# --------------------------------------------------------------------------- L1 threshold sealing
def test_l1_threshold_change_reseals_integrity_mac(client, identities, fake_db):
    row = {"id": uuid.UUID(MID), "ward_id": uuid.UUID(PID), "patient_id": None, "parameter": "spo2",
           "low_limit": 90, "high_limit": 100, "updated_at": NOW}
    fake_db.one = lambda sql, params: row if "returning" in sql else ({"ok": 1} if "wards" in sql else None)
    body = {"parameter": "spo2", "low_limit": 90, "high_limit": 100, "confirm": True}
    r = client.put(f"/v1/thresholds/wards/{PID}", headers=hdr(identities, "physician"), json=body)
    assert r.status_code == 200, r.text
    seal = [c for c in fake_db.calls if c[0] == "execute" and "integrity_mac" in c[1]]
    assert seal and seal[0][2] == (alarm_service.threshold_mac(row), MID)
    assert alarm_service.threshold_trusted({**row, "integrity_mac": seal[0][2][0]})


# --------------------------------------------------------------------------- A5 break-glass use audit
def test_a5_patient_read_through_break_glass_is_audited(client, identities, fake_db, recorded):
    patient = {"id": PID, "pseudonym": "PT-0001", "display_name": "A. B.", "birth_year": 1950, "ward_id": PID,
               "bed_label": "1", "monitor_serial": None, "active_alarms": 0, "admitted_at": NOW}
    fake_db.one = lambda sql, params: {"grant_id": MID} if "active_break_glass_grant" in sql else patient
    assert client.get(f"/v1/patients/{PID}", headers=hdr(identities, "nurse")).status_code == 200
    used = [e for e in recorded if e[0] == "break_glass.used"]
    assert used == [("break_glass.used", "patient", PID, "success")]


def test_a5_normal_ward_access_records_no_break_glass_use(client, identities, fake_db, recorded):
    patient = {"id": PID, "pseudonym": "PT-0001", "display_name": "A. B.", "birth_year": 1950, "ward_id": PID,
               "bed_label": "1", "monitor_serial": None, "active_alarms": 0, "admitted_at": NOW}
    fake_db.one = lambda sql, params: {"grant_id": None} if "active_break_glass_grant" in sql else patient
    assert client.get(f"/v1/patients/{PID}", headers=hdr(identities, "nurse")).status_code == 200
    assert not [e for e in recorded if e[0] == "break_glass.used"]


# --------------------------------------------------------------------------- I5 / I6 / I7 / W4
@pytest.mark.parametrize("path,role", [("/v1/wards", "nurse"), ("/v1/alarms", "nurse"), ("/v1/events", "nurse"),
                                       (f"/v1/files/patients/{PID}", "nurse"), ("/v1/staff", "admin"),
                                       ("/v1/alarms/monitor-states", "nurse"), (f"/v1/wards/{PID}/beds", "biomed_tech"),
                                       ("/v1/staff/role-requests", "admin")])
def test_i5_lists_are_bounded_page_objects(client, identities, fake_db, path, role):
    fake_db.one = {"ok": 1}
    r = client.get(path, headers=hdr(identities, role))
    assert r.status_code == 200, (path, r.text)
    assert set(r.json()) >= {"items", "next_offset"} and r.json()["items"] == []
    assert any("limit" in sql for sql in fake_db.sql)


def test_i5_integrity_and_advance_have_response_models():
    table = routes()
    for key in (("GET", "/v1/events/integrity"), ("GET", "/v1/events/signing-key"), ("GET", "/v1/events/alerts"),
                ("POST", "/v1/simulation/advance"), ("GET", "/v1/alarms/system-status")):
        assert table[key].response_model is not None, key


def test_i6_before_id_is_bounded_to_bigint(client, identities, fake_db):
    h = hdr(identities, "nurse")
    assert client.get("/v1/events", params={"before_id": 2**63}, headers=h).status_code == 422
    assert client.get("/v1/events", params={"before_id": 2**63 - 1}, headers=h).status_code == 200


def test_i7_upload_display_name_is_sanitised():
    from app.core.validation import safe_filename
    from app.services import files as file_service

    name = safe_filename(file_service.display_name("..\\..\\scan‮gpj.pdf"), default="upload")
    assert "/" not in name and "\\" not in name and "‮" not in name and name.endswith("pdf")
    source = (__import__("pathlib").Path(__file__).resolve().parents[1] / "app" / "routers" / "files.py").read_text("utf-8")
    assert "safe_filename(file_service.display_name(file.filename)" in source


def test_w4_patient_search_uses_json_body(client, identities, fake_db):
    h = hdr(identities, "nurse")
    r = client.post("/v1/patients/search", headers=h, json={"q": "Smith", "limit": 10})
    assert r.status_code == 200 and r.json() == {"items": [], "next_offset": None}
    params = fake_db.calls[-1][2]
    assert params["q"] == "%Smith%" and params["limit"] == 11
    assert client.post("/v1/patients/search", headers=h, json={"q": "x", "role": "admin"}).status_code == 422
    assert client.post("/v1/patients/search", headers=h, json={"limit": 1000}).status_code == 422


# --------------------------------------------------------------------------- F1 / F3 / N3 devices
def test_f1_beds_of_out_of_scope_ward_is_404(client, identities, fake_db):
    fake_db.one = None
    assert client.get(f"/v1/wards/{PID}/beds", headers=hdr(identities, "nurse")).status_code == 404


def test_f1_beds_report_occupancy(client, identities, fake_db):
    fake_db.one = {"ok": 1}
    fake_db.rows = [{"id": PID, "ward_id": PID, "label": "Bed 1", "patient_id": None, "patient_pseudonym": None,
                     "monitor_id": MID, "monitor_serial": "MX-1"}]
    body = client.get(f"/v1/wards/{PID}/beds", headers=hdr(identities, "biomed_tech")).json()
    assert body["items"][0]["occupied"] is True and body["items"][0]["monitor_serial"] == "MX-1"


def test_f3_admin_reads_maintenance_but_cannot_record_it(client, identities, fake_db):
    assert Perm.MAINTENANCE_READ in PERMISSIONS[Role.ADMIN] and Perm.MAINTENANCE_WRITE not in PERMISSIONS[Role.ADMIN]
    assert Perm.MAINTENANCE_READ in PERMISSIONS[Role.BIOMED_TECH]
    h = hdr(identities, "admin")
    assert client.get(f"/v1/monitors/{MID}/maintenance", headers=h).status_code == 200
    assert client.post(f"/v1/monitors/{MID}/maintenance", headers=h, json={"kind": "inspection"}).status_code == 403
    assert client.get(f"/v1/monitors/{MID}/maintenance", headers=hdr(identities, "nurse")).status_code == 403


def test_n3_binding_requires_pairing_code(client, identities, fake_db):
    h = hdr(identities, "biomed_tech")
    assert client.post(f"/v1/monitors/{MID}/assignment", headers=h, json={"bed_id": PID, "confirm": True}).status_code == 422
    assert client.post(f"/v1/monitors/{MID}/assignment", headers=h,
                       json={"bed_id": PID, "confirm": True, "pairing_code": "short"}).status_code == 422


def test_n3_wrong_pairing_code_is_audited_and_refused(client, identities, fake_db, monkeypatch, recorded):
    async def deny(conn, monitor_id, code):
        raise device_auth.DeviceAuthError("device authentication failed")

    monkeypatch.setattr(device_auth, "verify_in_db", deny)
    h = hdr(identities, "biomed_tech")
    r = client.post(f"/v1/monitors/{MID}/assignment", headers=h,
                    json={"bed_id": PID, "confirm": True, "pairing_code": "A" * 8 + "b" * 8 + "123"})
    assert r.status_code == 403 and r.json()["code"] == "device_auth_failed"
    assert ("monitor.auth_failed", "monitor", MID, "failure") in recorded
    assert not any("monitor_assignments" in sql for sql in fake_db.sql)  # nothing bound


def test_n3_correct_pairing_code_proceeds_to_binding(client, identities, fake_db, monkeypatch):
    seen = []

    async def ok(conn, monitor_id, code):
        seen.append((str(monitor_id), code))

    monkeypatch.setattr(device_auth, "verify_in_db", ok)
    fake_db.one = None  # monitor lookup -> 404 after a successful device check
    code = "Pairing_Code-0123456789"
    r = client.post(f"/v1/monitors/{MID}/assignment", headers=hdr(identities, "biomed_tech"),
                    json={"bed_id": PID, "confirm": True, "pairing_code": code})
    assert seen == [(MID, code)] and r.status_code == 404


# --------------------------------------------------------------------------- A4 two-person rule
def test_a4_admin_promotion_requires_role_request(client, identities, fake_db):
    fake_db.one = {"role": "nurse", "is_active": True}
    r = client.patch(f"/v1/staff/{PID}", headers=hdr(identities, "admin"), json={"role": "admin"})
    assert r.status_code == 409 and r.json()["code"] == "approval_required"


def test_a4_requester_cannot_approve_own_request(client, identities, fake_db):
    uid = add_identity(identities, "admin")
    fake_db.one = {"target_user_id": PID, "new_role": "admin", "requested_by": uid, "status": "pending"}
    r = client.post(f"/v1/staff/role-requests/{MID}/approve", headers=hdr(identities, "admin", uid=uid))
    assert r.status_code == 403
    assert not any("update public.staff_profiles" in sql for sql in fake_db.sql)


def test_a4_second_admin_approval_applies_role(client, identities, fake_db, recorded):
    requester = str(uuid.uuid4())
    staff = {"user_id": PID, "email": "n@example.test", "full_name": "N", "role": "admin", "is_active": True,
             "ward_ids": [], "last_login_at": None}
    fake_db.one = lambda sql, params: ({"target_user_id": PID, "new_role": "admin", "requested_by": requester,
                                        "status": "pending"} if "staff_role_requests" in sql else staff)
    r = client.post(f"/v1/staff/role-requests/{MID}/approve", headers=hdr(identities, "admin"))
    assert r.status_code == 200 and r.json()["role"] == "admin"
    sql = " ".join(fake_db.sql)
    assert "status = 'approved'" in sql and "update public.staff_profiles set role" in sql
    assert any(e[0] == "staff.role_change_approved" for e in recorded)


def test_a4_cannot_request_own_role_change(client, identities, fake_db):
    uid = add_identity(identities, "admin")
    r = client.post(f"/v1/staff/{uid}/role-requests", headers=hdr(identities, "admin", uid=uid), json={"new_role": "nurse"})
    assert r.status_code == 403


# --------------------------------------------------------------------------- P7 small counts
def test_p7_ward_report_suppresses_small_counts(client, identities, monkeypatch, fake_db):
    from app.services import reports

    async def fake_activity(conn, ward_id, start, end):
        return {"ward_id": None, "period_start": NOW, "period_end": NOW, "alarm_counts": {"low_spo2": 2, "high_hr": 9},
                "mean_time_to_ack_seconds": None, "unacknowledged_high_priority": 0, "readings_count": 0,
                "generated_at": NOW}

    monkeypatch.setattr(reports, "ward_activity", fake_activity)
    r = client.get("/v1/reports/ward-activity", headers=hdr(identities, "physician"))
    assert r.status_code == 200 and r.json()["alarm_counts"] == {"low_spo2": None, "high_hr": 9}


# --------------------------------------------------------------------------- L2 / N4 / I3 configuration
BASE = dict(supabase_url="https://x.supabase.co", supabase_anon_key="anon-key-value",
            supabase_service_role_key="service-role-key-0123456789", supabase_jwt_secret="jwt-secret-0123456789-abcdefghijKLMN")


def test_l2_optional_key_material_is_secret():
    s = Settings(**BASE, app_env="test", database_url="postgresql://acme_api:pw@h/db?sslmode=verify-full",
                 audit_signing_key="pem-value", config_integrity_key="k" * 40)
    assert "pem-value" not in repr(s) and s.config_integrity_key.get_secret_value() == "k" * 40
    example = (__import__("pathlib").Path(__file__).resolve().parents[1] / ".env.example").read_text("utf-8")
    assert "AUDIT_SIGNING_KEY=" in example and "CONFIG_INTEGRITY_KEY=" in example and "ALLOWED_HOSTS=" in example


@pytest.mark.parametrize("override", [
    {"database_url": "postgresql://acme_api:pw@h/db?sslmode=verify-full"},                  # weak DB password
    {"database_url": "postgresql://postgres:Str0ng-Passw0rd-xyz@h/db?sslmode=verify-full"},  # superuser
    {"supabase_jwt_secret": "short-secret"},
    {"supabase_service_role_key": "changeme"},
])
def test_n4_production_refuses_weak_secrets(override):
    good = {**BASE, "database_url": "postgresql://acme_api:Str0ng-Passw0rd-xyz@h/db?sslmode=verify-full"}
    Settings(**good, app_env="production")  # baseline is accepted
    with pytest.raises(ValueError):
        Settings(**{**good, **override}, app_env="production")
    Settings(**{**good, **override}, app_env="test")  # non-production keeps working


def test_i3_allowed_hosts_setting_reaches_middleware(monkeypatch):
    import app.main as main

    s = Settings(**BASE, app_env="test", database_url="postgresql://acme_api:pw@h/db?sslmode=verify-full",
                 allowed_hosts="api.acme.example, testserver")
    assert s.allowed_hosts == ["api.acme.example", "testserver"]
    monkeypatch.setattr(main, "get_settings", lambda: s)
    from fastapi.testclient import TestClient

    with TestClient(main.create_app()) as c:
        assert c.get("/v1/health").status_code == 200
        assert c.get("/v1/health", headers={"Host": "evil.vercel.app"}).status_code == 400


# --------------------------------------------------------------------------- N2 failed sign-ins
def test_n2_session_start_reports_failed_sign_ins(client, identities, monkeypatch):
    from contextlib import asynccontextmanager

    class Conn:
        async def execute(self, sql, params=()):
            return None

    @asynccontextmanager
    async def tx(principal, read_only=False):
        yield Conn()

    async def one(conn, sql, params=()):
        if "register_session" in sql:
            return {"status": "active", "created": True, "revoked_count": 0, "previous_unclosed": False}
        if "session_state" in sql:
            from datetime import UTC, datetime
            now = datetime.now(UTC)
            return {"created_at": now, "last_activity_at": now, "revoked_at": None, "auth_session_exists": True,
                    "idle_minutes": 15, "absolute_hours": 12}
        if "login_activity_summary" in sql:
            return {"failed_since_previous_login": 3, "last_failed_at": None}
        return {"last_login_at": None, "ip": None}

    monkeypatch.setattr(auth_router, "transaction", tx)
    monkeypatch.setattr(auth_router, "fetch_one", one)
    r = client.post("/v1/auth/session", headers=hdr(identities, "nurse"))
    assert r.status_code == 200 and r.json()["failed_since_previous_login"] == 3


# --------------------------------------------------------------------------- I4 read-only transactions
def test_i4_pure_reads_use_read_only_transactions():
    import inspect

    from app import db
    from app.routers import maintenance, monitors, simulation as sim_router, staff, thresholds, wards

    assert "set transaction read only" in inspect.getsource(db.transaction)
    for fn in (wards.list_wards, wards.list_beds, thresholds.list_thresholds, monitors.list_monitors,
               maintenance.list_maintenance, staff.list_staff, staff.list_role_requests, sim_router.get_state):
        assert "read_only=True" in inspect.getsource(fn), fn.__name__
