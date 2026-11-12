"""API-security tests (skills/api-security countermeasures): exposure, throttling, JSON format,
message size, HTTP verbs."""

from __future__ import annotations

import re
import uuid
from typing import get_origin

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.middleware import MAX_JSON_BODY_BYTES, RateLimitMiddleware
from app.main import create_app
from tests.conftest import make_token
from tests.test_input_validation import MID, PID, auth, fake_db  # noqa: F401 - fixture re-export

OWNED_PREFIXES = ("/v1/patients", "/v1/thresholds", "/v1/monitors")


def _routes() -> list[APIRoute]:
    return [r for r in create_app().routes if isinstance(r, APIRoute)]


def _fill(path: str) -> str:
    return re.sub(r"{\w+}", PID, path)


# --------------------------------------------------------------------------- T2140 sensitive data exposure
KNOWN_WITHOUT_RESPONSE_MODEL = {"/v1/break-glass/pending-review", "/v1/events/integrity", "/v1/simulation/advance"}
FORBIDDEN_KEYS = re.compile(r"(password|secret|token|hash|service_role|encrypted|raw_user_meta|refresh|api_?key|stack|traceback)", re.I)
POLICY_FIELDS = {"password_min_length"}  # a password *policy* value, not a credential


def test_t2140_every_route_declares_a_response_model():
    missing = {r.path for r in _routes() if r.status_code != 204 and r.response_model is None and r.path != "/v1/health"}
    assert not {p for p in missing if p.startswith(OWNED_PREFIXES)}, missing
    assert missing <= KNOWN_WITHOUT_RESPONSE_MODEL, missing


def test_t2140_response_schemas_hold_no_secret_fields():
    comps = create_app().openapi()["components"]["schemas"]
    for name, schema in comps.items():
        for field in schema.get("properties", {}):
            assert field in POLICY_FIELDS or not FORBIDDEN_KEYS.search(field), (name, field)


def test_t2140_internal_errors_are_generic(identities, fake_db, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError('syntax error at or near "SELECT" (psycopg.errors.SyntaxError) SQLSTATE 42601')

    monkeypatch.setattr("app.routers.patients.fetch_all", boom)
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        r = c.get("/v1/patients", headers=auth(identities, "nurse"))
    assert r.status_code == 500
    body = r.json()
    assert {"error", "request_id"} <= set(body) <= {"error", "request_id", "code"}
    assert "syntax" not in r.text.lower() and "psycopg" not in r.text.lower() and "select" not in r.text.lower()


def test_t2140_biomed_tech_cannot_read_patient_data(client, identities, fake_db):
    h = auth(identities, "biomed_tech")
    for path in ("/v1/patients", f"/v1/patients/{PID}", f"/v1/patients/{PID}/observations", f"/v1/patients/{PID}/readings"):
        assert client.get(path, headers=h).status_code == 403
    assert fake_db.calls == []


# --------------------------------------------------------------------------- T1363 throttling
def test_t1363_unauthenticated_requests_throttled_with_retry_after(client):
    codes = [client.get("/v1/wards").status_code for _ in range(31)]
    assert codes[:30] == [401] * 30
    r = client.get("/v1/wards")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.json() == {"error": "Too many requests. Please slow down."}


def test_t1363_spoofed_x_forwarded_for_does_not_reset_bucket(client):
    for i in range(30):
        client.get("/v1/wards", headers={"X-Forwarded-For": f"10.0.0.{i}"})
    assert client.get("/v1/wards", headers={"X-Forwarded-For": "10.9.9.9"}).status_code == 429


def test_t1363_auth_route_has_stricter_per_route_limit(client, identities):
    codes = [client.post("/v1/auth/session").status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    assert client.get("/v1/health").status_code == 200  # other routes keep their own budget


def test_t1363_simulation_reset_limited_per_user(client, identities, fake_db):
    h = auth(identities, "admin")
    codes = [client.post("/v1/simulation/reset", json={}, headers=h).status_code for _ in range(4)]
    assert codes[:3] != [429] * 3 and codes[3] == 429
    other = auth(identities, "admin")
    assert client.post("/v1/simulation/reset", json={}, headers=other).status_code != 429


def test_t1363_token_rotation_hits_ip_ceiling():
    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/x", ok)])
    app.add_middleware(RateLimitMiddleware, per_minute=5, auth_per_minute=2, ip_ceiling_factor=2)
    with TestClient(app) as c:
        codes = [c.get("/x", headers={"Authorization": f"Bearer {make_token()}"}).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


# --------------------------------------------------------------------------- T167 JSON hijacking
KNOWN_LIST_RESPONSES_ELSEWHERE = {"/v1/alarms", "/v1/alarms/monitor-states", "/v1/events", "/v1/files/patients/{patient_id}", "/v1/staff", "/v1/wards",
                                  "/v1/break-glass/mine", "/v1/break-glass/pending-review"}  # see CROSS-OWNER requests


def test_t167_no_route_returns_a_top_level_array():
    lists = {r.path for r in _routes() if r.response_model is not None and get_origin(r.response_model) is list}
    assert not {p for p in lists if p.startswith(OWNED_PREFIXES)}, lists
    assert lists <= KNOWN_LIST_RESPONSES_ELSEWHERE, lists


@pytest.mark.parametrize("path,role", [("/v1/patients", "nurse"), (f"/v1/patients/{PID}/observations", "nurse"),
                                       (f"/v1/patients/{PID}/readings", "nurse"), ("/v1/thresholds", "nurse"),
                                       ("/v1/monitors", "biomed_tech"), (f"/v1/monitors/{MID}/maintenance", "biomed_tech"),
                                       ("/v1/patients", None), ("/v1/nope", "nurse")])
def test_t167_json_responses_are_objects_with_nosniff(client, identities, fake_db, path, role):
    fake_db.one = {"?column?": 1}
    r = client.get(path, headers=auth(identities, role) if role else {})
    assert r.headers["content-type"].startswith("application/json")
    assert r.text.lstrip()[:1] == "{"
    assert r.headers["x-content-type-options"] == "nosniff"


# --------------------------------------------------------------------------- T537 / T228 message size
def test_t537_body_limit_declared_and_chunked(client, identities, fake_db):
    h = {**auth(identities, "nurse"), "Content-Type": "application/json"}
    big = b'{"body": "' + b"a" * MAX_JSON_BODY_BYTES + b'"}'
    assert client.post(f"/v1/patients/{PID}/observations", content=big, headers=h).status_code == 413

    def chunks():
        yield b'{"body": "'
        for _ in range(80):
            yield b"a" * 1024
        yield b'"}'

    r = client.post(f"/v1/patients/{PID}/observations", content=chunks(), headers=h)
    assert r.status_code == 413
    assert fake_db.calls == []
    under = b'{"body": "' + b"a" * 2000 + b'"}'
    assert client.post(f"/v1/patients/{PID}/observations", content=under, headers=h).status_code != 413


def test_t537_overlong_fields_and_lists_rejected(client, identities, fake_db):
    assert client.post(f"/v1/patients/{PID}/observations", json={"body": "a" * 2001},
                       headers=auth(identities, "nurse")).status_code == 422
    r = client.post("/v1/simulation/scenario", json={"scenario": "normal", "monitor_ids": [str(uuid.uuid4()) for _ in range(11)]},
                    headers=auth(identities, "admin"))
    assert r.status_code == 422


def test_t228_header_and_url_limits_apply_before_auth(client, identities):
    h = auth(identities, "nurse")
    many = {**h, **{f"x-h{i}": "a" for i in range(70)}}
    assert client.get("/v1/patients", headers=many).status_code == 431
    assert client.get("/v1/patients", headers={**h, "x-big": "a" * 17_000}).status_code == 431
    assert client.get("/v1/patients?q=" + "a" * 3000, headers=h).status_code == 414
    assert client.get("/v1/patients?q=" + "a" * 3000).status_code == 414  # rejected even without a token


# --------------------------------------------------------------------------- T65 / T113 verbs
@pytest.mark.parametrize("verb", ["TRACE", "CONNECT", "PWRLWA", "HEAD", "PROPFIND"])
def test_t65_unlisted_verbs_rejected_everywhere(client, verb):
    for path in ("/v1/health", "/v1/patients", "/v1/staff"):
        r = client.request(verb, path)
        assert r.status_code == 405
        if verb != "HEAD":
            assert "TRACE" not in r.headers.get("allow", "") and "GET" in r.headers.get("allow", "")


@pytest.mark.parametrize("header", ["X-HTTP-Method-Override", "X-HTTP-Method", "X-Method-Override"])
def test_t65_method_override_headers_rejected(client, identities, fake_db, header):
    r = client.get("/v1/patients", headers={**auth(identities, "nurse"), header: "DELETE"})
    assert r.status_code == 400
    assert fake_db.calls == []


def test_t65_cors_preflight_advertises_explicit_methods(client):
    r = client.options("/v1/patients", headers={"Origin": "https://acme-clinical.vercel.app", "Access-Control-Request-Method": "GET"})
    allowed = r.headers["access-control-allow-methods"]
    assert "*" not in allowed and "TRACE" not in allowed and "GET" in allowed


@pytest.mark.parametrize("route_path,methods", sorted({(r.path, tuple(sorted(r.methods))) for r in _routes()}))
@pytest.mark.parametrize("verb", ["PWRLWA", "TRACE", "HEAD", "PUT", "OPTIONS", "GET", "POST", "PATCH", "DELETE"])
def test_t113_verb_tampering_never_reaches_protected_data(client, fake_db, route_path, methods, verb):
    r = client.request(verb, _fill(route_path), json={} if verb in ("POST", "PUT", "PATCH") else None)
    if route_path == "/v1/health" and verb == "GET":
        assert r.status_code == 200
        return
    assert r.status_code in (400, 401, 403, 404, 405), (verb, route_path, r.status_code)
    assert b'"items"' not in r.content
    assert fake_db.calls == []


def test_t113_role_enforced_for_every_verb(client, identities, fake_db):
    h = auth(identities, "nurse")
    for verb, path in (("POST", "/v1/staff"), ("PATCH", f"/v1/staff/{PID}"), ("DELETE", f"/v1/staff/{PID}"),
                       ("PUT", f"/v1/thresholds/wards/{PID}"), ("DELETE", f"/v1/monitors/{MID}/assignment")):
        assert client.request(verb, path, json={}, headers=h).status_code in (403, 405), (verb, path)
    assert not any(kind == "execute" or "insert" in sql for kind, sql, _ in fake_db.calls)


# --------------------------------------------------------------------------- T1542 state changes never via GET
# Verb-like final path segments that would indicate an action exposed through GET.
ACTION_WORDS = re.compile(r"/(ack|acknowledge|reset|advance|logout|delete|remove|bind|unbind|assign|assignment|create|update|"
                          r"approve|grant|upload|scenario)/?$", re.I)


def test_t1542_get_routes_are_read_only_by_construction():
    for r in _routes():
        if r.methods & {"GET", "HEAD"}:
            assert not r.methods & {"POST", "PUT", "PATCH", "DELETE"}, r.path
            assert not ACTION_WORDS.search(r.path), r.path


@pytest.mark.parametrize("path", [f"/v1/alarms/{PID}/acknowledge", f"/v1/monitors/{MID}/assignment", "/v1/simulation/reset",
                                  "/v1/simulation/advance", "/v1/auth/logout", f"/v1/thresholds/wards/{PID}"])
def test_t1542_get_on_action_paths_is_405(client, identities, fake_db, path):
    assert client.get(path, headers=auth(identities, "admin")).status_code == 405
    assert fake_db.calls == []


@pytest.mark.parametrize("path,role", [("/v1/patients", "nurse"),
                                       (f"/v1/patients/{PID}/observations", "nurse"), (f"/v1/patients/{PID}/readings", "nurse"),
                                       ("/v1/thresholds", "nurse"), ("/v1/monitors", "biomed_tech"),
                                       (f"/v1/monitors/{MID}/maintenance", "biomed_tech")])
def test_t1542_owned_get_handlers_issue_only_selects(client, identities, fake_db, path, role):
    fake_db.one = {"?column?": 1}
    client.get(path, headers=auth(identities, role))
    assert fake_db.calls, path
    for kind, sql, _ in fake_db.calls:
        assert kind != "execute" and sql.lstrip().lower().startswith("select"), (path, sql[:40])


def test_t1542_owned_state_changes_use_unsafe_methods():
    expected = {("/v1/patients/{patient_id}/observations", "POST"), ("/v1/thresholds/wards/{ward_id}", "PUT"),
                ("/v1/thresholds/patients/{patient_id}", "PUT"), ("/v1/monitors/{monitor_id}/assignment", "POST"),
                ("/v1/monitors/{monitor_id}/assignment", "DELETE"), ("/v1/monitors/{monitor_id}/maintenance", "POST")}
    actual = {(r.path, m) for r in _routes() for m in r.methods}
    assert expected <= actual
