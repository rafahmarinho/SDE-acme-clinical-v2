"""Foundation security tests: headers, authentication, central authorization, alarm semantics."""

import time

import pytest

from app.core.security import PERMISSIONS, Perm, Role
from app.services import alarms
from tests.conftest import add_identity, make_token


def test_security_headers_and_no_server_banner(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    for header in ("strict-transport-security", "x-content-type-options", "x-frame-options", "content-security-policy",
                   "referrer-policy", "cache-control"):
        assert header in r.headers
    assert r.headers["cache-control"] == "no-store, no-cache, max-age=0, must-revalidate, private"
    assert r.headers["expires"] == "0" and r.headers["pragma"] == "no-cache"
    assert "server" not in r.headers
    assert r.headers["x-request-id"]


def test_unknown_method_rejected(client):
    assert client.request("TRACE", "/v1/health").status_code == 405


def test_cors_only_allows_configured_origin(client):
    ok = client.options("/v1/me", headers={"Origin": "https://acme-clinical.vercel.app", "Access-Control-Request-Method": "GET"})
    bad = client.options("/v1/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "https://acme-clinical.vercel.app"
    assert "access-control-allow-origin" not in bad.headers


def test_oversized_body_rejected(client):
    r = client.post("/v1/auth/session", content=b"x" * 2_000_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413


@pytest.mark.parametrize("token_kwargs", [
    {"secret": "wrong-secret-wrong-secret-wrong-secret"},
    {"aud": "anon"},
    {"iss": "https://evil.supabase.co/auth/v1"},
    {"exp_in": -120},
])
def test_invalid_tokens_rejected(client, identities, token_kwargs):
    uid = add_identity(identities, "nurse")
    r = client.get("/v1/wards", headers={"Authorization": f"Bearer {make_token(uid, **token_kwargs)}"})
    assert r.status_code == 401
    assert r.json()["error"] == "Authentication required."


def test_missing_token_and_unknown_or_inactive_user(client, identities):
    assert client.get("/v1/wards").status_code == 401
    assert client.get("/v1/wards", headers={"Authorization": f"Bearer {make_token()}"}).status_code == 401
    inactive = add_identity(identities, "nurse", active=False)
    assert client.get("/v1/wards", headers={"Authorization": f"Bearer {make_token(inactive)}"}).status_code == 401


def test_absolute_session_timeout(client, identities):
    uid = add_identity(identities, "nurse", absolute_hours=1)
    old = int(time.time()) - 2 * 3600
    token = make_token(uid, iat=int(time.time()), auth_time=old)
    assert client.get("/v1/wards", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_admin_requires_mfa(client, identities):
    uid = add_identity(identities, "admin")
    r = client.get("/v1/staff", headers={"Authorization": f"Bearer {make_token(uid, aal='aal1')}"})
    assert r.status_code == 403


def test_forbidden_is_audited_and_generic(client, identities):
    uid = add_identity(identities, "biomed_tech")
    r = client.get("/v1/staff", headers={"Authorization": f"Bearer {make_token(uid)}"})
    assert r.status_code == 403
    assert r.json()["error"] == "You do not have permission to perform this action."
    assert ("authz.denied", "route", "/v1/staff", "denied") in identities["__events__"]


def test_permission_matrix_separation_of_duties():
    assert Perm.STAFF_MANAGE in PERMISSIONS[Role.ADMIN]
    assert Perm.ALARM_ACK not in PERMISSIONS[Role.ADMIN]          # admins don't act clinically
    assert Perm.OBSERVATION_WRITE not in PERMISSIONS[Role.ADMIN]
    assert Perm.STAFF_MANAGE not in PERMISSIONS[Role.PHYSICIAN]
    assert Perm.PATIENT_READ not in PERMISSIONS[Role.BIOMED_TECH]  # device work only
    assert Perm.THRESHOLD_WRITE not in PERMISSIONS[Role.NURSE]


def test_validation_errors_do_not_echo_input(client, identities):
    uid = add_identity(identities, "physician")
    r = client.put("/v1/thresholds/wards/00000000-0000-4000-8000-000000000001",
                   json={"parameter": "spo2", "low_limit": 99, "high_limit": 50, "confirm": True, "role": "admin<script>"},
                   headers={"Authorization": f"Bearer {make_token(uid, auth_time=int(time.time()))}"})
    assert r.status_code == 422
    assert "<script>" not in r.text


def test_vital_alarm_evaluation_and_invalid_quality():
    limits = {"spo2": (92, 100), "heart_rate": (50, 120)}
    conds = alarms.evaluate_vitals({"spo2": 85, "heart_rate": 130, "quality": "good"}, limits)
    assert {c.type for c in conds} == {"low_spo2", "high_heart_rate"}
    assert all(c.priority == "high" for c in conds)
    assert alarms.evaluate_vitals({"spo2": 10, "quality": "invalid"}, limits) == []


def test_device_conditions_priority():
    assert alarms.evaluate_device(100, None, connected=False)[0].type == "connection_lost"
    assert [c.type for c in alarms.evaluate_device(15, "good", True)] == ["low_battery"]
    assert alarms.evaluate_device(5, "invalid", True)[0].priority == "medium"
