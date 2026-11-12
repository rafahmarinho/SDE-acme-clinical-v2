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
    assert missing == set(), missing  # T2139: every route serialises through an explicit response model


def test_t2139_staff_directory_and_emails_only_for_administrators(client, identities, fake_db):
    assert client.get("/v1/staff", headers=auth(identities, "nurse")).status_code == 403
    assert client.get("/v1/staff", headers=auth(identities, "physician")).status_code == 403
    assert fake_db.calls == []
    fake_db.rows = [{"user_id": str(uuid.uuid4()), "email": "nora@acme.test", "full_name": "Nora L", "role": "nurse",
                     "is_active": True, "ward_ids": [], "last_login_at": None, "secret_hash": "x", "mfa_secret": "y"}]
    r = client.get("/v1/staff", headers=auth(identities, "admin"))
    assert r.status_code == 200 and r.json()["items"][0]["email"] == "nora@acme.test"
    assert "secret_hash" not in r.text and "mfa_secret" not in r.text  # extra columns never leak


def test_t2139_forced_500_returns_only_the_error_envelope(identities, fake_db, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("relation secret_table at /srv/app.py line 3")

    monkeypatch.setattr("app.routers.patients.fetch_all", boom)
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        r = c.get("/v1/patients", headers=auth(identities, "nurse"))
    assert r.status_code == 500 and set(r.json()) <= {"error", "request_id", "code"}
    assert "secret_table" not in r.text and "app.py" not in r.text


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
def test_t167_t166_no_route_returns_a_top_level_array():
    lists = {r.path for r in _routes() if r.response_model is not None and get_origin(r.response_model) is list}
    assert lists == set(), lists  # every collection is wrapped in the Page object envelope


@pytest.mark.parametrize("path", ["/v1/patients", "/v1/alarms", "/v1/events", "/v1/staff", "/v1/wards", "/v1/me"])
def test_t166_cookie_only_requests_are_unauthenticated(client, fake_db, path):
    r = client.get(path, cookies={"sb-access-token": make_token(), "session": "x"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/json") and r.headers["x-content-type-options"] == "nosniff"
    assert fake_db.calls == []


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
    if route_path == "/v1/csp-report" and verb == "POST":  # public report sink: 204, no data, no DB access
        assert r.status_code == 204 and r.content == b"" and fake_db.calls == []
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


# --------------------------------------------------------------------------- T1362 shared per-user throttling
def _shared_limit_env(monkeypatch):
    """Simulation router on a fake DB that emulates public.consume_rate_limit (per verified user, per window)."""
    from contextlib import asynccontextmanager
    from datetime import UTC, datetime

    from app.core import ratelimit
    from app.routers import simulation as sim_router

    hits: dict[tuple[str, str], int] = {}

    class Conn:
        def __init__(self, user_id):
            self.user_id = user_id

    @asynccontextmanager
    async def fake_tx(principal, read_only=False):
        yield Conn(str(principal.user_id))

    async def fake_one(conn, sql, params=()):
        if sql == ratelimit.SHARED_LIMIT_SQL:
            name, per_minute = params
            key = (name, conn.user_id)  # keyed on app.user_id, never on the token or a client value
            hits[key] = hits.get(key, 0) + 1
            return {"retry_after": 42 if hits[key] > per_minute else 0}
        return {"scenario": "normal", "tick": 0, "version": 1, "updated_at": datetime.now(UTC)}

    async def nothing(*a, **k):
        return None

    monkeypatch.setattr(sim_router, "transaction", fake_tx)
    monkeypatch.setattr(sim_router, "fetch_one", fake_one)
    monkeypatch.setattr(sim_router.simulation, "reset", nothing)
    monkeypatch.setattr(sim_router, "record_event", nothing)
    return hits


def test_t1362_seventh_reset_by_same_user_is_429_even_with_rotated_tokens(client, identities, monkeypatch):
    import time as _time

    from tests.conftest import add_identity

    hits = _shared_limit_env(monkeypatch)
    uid = add_identity(identities, "admin")
    body = {"confirm_text": "RESET DEMO DATA", "acknowledged": True}
    responses = []
    for _ in range(7):
        # a fresh token per request defeats the per-instance token-hash bucket; the shared per-user budget holds
        token = make_token(uid, aal="aal2", auth_time=int(_time.time()), jti=str(uuid.uuid4()))
        responses.append(client.post("/v1/simulation/reset", json=body, headers={"Authorization": f"Bearer {token}"}))
    codes = [r.status_code for r in responses]
    assert codes[:3] == [200, 200, 200], codes
    assert codes[6] == 429 and responses[6].headers["Retry-After"] == "42"
    assert hits[("simulation-reset", uid)] == 7
    other = add_identity(identities, "admin")
    token = make_token(other, aal="aal2", auth_time=int(_time.time()))
    assert client.post("/v1/simulation/reset", json=body, headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_t1362_shared_store_function_keys_on_verified_caller_and_is_locked_down():
    from pathlib import Path

    from app.core import ratelimit

    sql = (Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0009_rate_limits.sql").read_text(encoding="utf-8")
    assert "current_setting('app.user_id', true)" in sql and "on conflict (bucket, window_start)" in sql
    assert "security definer set search_path" in sql
    assert "revoke execute on function public.consume_rate_limit(text, integer) from public, anon, authenticated" in sql
    assert {"simulation", "simulation-reset", "reports", "files-upload"} <= set(ratelimit.SHARED_LIMITS)
    for module in ("simulation", "reports"):
        source = (Path(ratelimit.__file__).resolve().parents[1] / "routers" / f"{module}.py").read_text(encoding="utf-8")
        assert "enforce_shared_limit(conn" in source, module


def test_t1362_supabase_auth_rate_limits_are_explicit():
    from pathlib import Path

    toml = (Path(__file__).resolve().parents[2] / "supabase" / "config.toml").read_text(encoding="utf-8")
    section = toml.split("[auth.rate_limit]", 1)[1].split("\n[", 1)[0]
    for key in ("email_sent", "sign_in_sign_ups", "token_verifications", "token_refresh"):
        assert re.search(rf"^{key}\s*=\s*\d+", section, re.M), key


def test_t2139_no_select_star_from_tables():
    from pathlib import Path

    offenders = []
    for path in (Path(__file__).resolve().parents[1] / "app").rglob("*.py"):
        for m in re.finditer(r"select\s+(?:\w+\.)?\*\s+from\s+([\w.]+)(\()?", path.read_text(encoding="utf-8"), re.I):
            if not m.group(2):  # set-returning functions (fixed OUT columns) are allowed, tables are not
                offenders.append(f"{path.name}: {m.group(0)}")
    assert offenders == []


# --------------------------------------------------------------------------- T536 incoming message size
def test_t536_65kb_json_and_deep_nesting_rejected(client, identities, fake_db):
    h = {**auth(identities, "nurse"), "Content-Type": "application/json"}
    big = b'{"body": "' + b"a" * (65 * 1024) + b'"}'
    assert client.post(f"/v1/patients/{PID}/observations", content=big, headers=h).status_code == 413
    nested = b'{"body": ' + b'{"a": ' * 200 + b"1" + b"}" * 200 + b"}"
    assert client.post(f"/v1/patients/{PID}/observations", content=nested, headers=h).status_code in (400, 413, 422)
    assert fake_db.calls == []


def test_t536_upload_over_limit_is_413_before_reaching_storage(client, identities, fake_db):
    from app.services import files as file_service

    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (6 * 1024 * 1024)
    r = client.post(f"/v1/files/patients/{PID}", files={"file": ("big.png", big, "image/png")},
                    headers=auth(identities, "nurse"))
    assert r.status_code == 413
    assert fake_db.calls == []
    assert len(big) > file_service.MAX_BYTES


def test_t536_storage_bucket_limit_matches_application_limit():
    from pathlib import Path

    from app.services import files as file_service

    sql = (Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "0002_roles_rls.sql").read_text(encoding="utf-8")
    m = re.search(r"values \('clinical-files', 'clinical-files', false, (\d+),", sql)
    assert m and int(m.group(1)) == file_service.MAX_BYTES


# --------------------------------------------------------------------------- T35 HTTP server settings
def test_t35_url_and_header_limits_emit_http_limit_violation(client, identities, caplog):
    import logging as _logging

    h = auth(identities, "nurse")
    with caplog.at_level(_logging.WARNING, logger="acme.security"):
        assert client.get("/v1/patients?q=" + "a" * 3 * 1024, headers=h).status_code == 414
        assert client.get("/v1/patients", headers={**h, **{f"x-h{i}": "a" for i in range(80)}}).status_code == 431
    events = [r for r in caplog.records if r.getMessage() == "http_limit_violation"]
    assert sorted(r.status for r in events) == [414, 431]
    assert all("aaaa" not in str(vars(r)) for r in events)  # the oversized values themselves are never logged


def test_t35_sustained_violations_alert_administrators_once(monkeypatch):
    from app.core import audit
    from app.core import middleware as mw

    alerts: list[tuple[str, dict]] = []

    async def fake_notify(kind, details=None):
        alerts.append((kind, details or {}))

    monkeypatch.setattr(audit, "notify_admins", fake_notify)

    async def ok(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/x", ok)])
    app.add_middleware(mw.SecurityHeadersMiddleware)
    with TestClient(app) as c:
        for _ in range(mw.LIMIT_ALERT_THRESHOLD):
            assert c.get("/x?q=" + "a" * (mw.MAX_URL_BYTES + 1)).status_code == 414
        assert c.get("/x").status_code == 200
    assert [k for k, _ in alerts] == ["http_limit_violation"]
    assert alerts[0][1]["status"] == 414


def test_t35_timeouts_are_configured():
    import json as _json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    functions = _json.loads((root / "backend" / "vercel.json").read_text(encoding="utf-8"))["functions"]
    assert 1 <= functions["api/index.py"]["maxDuration"] <= 60
    roles = (root / "supabase" / "migrations" / "0002_roles_rls.sql").read_text(encoding="utf-8")
    assert "alter role acme_api set statement_timeout" in roles
    assert "alter role acme_api set idle_in_transaction_session_timeout" in roles
    db = (root / "backend" / "app" / "db.py").read_text(encoding="utf-8")
    assert '"connect_timeout": 5' in db and "timeout=5" in db


def test_t35_statement_timeout_maps_to_generic_503(identities, fake_db, monkeypatch):
    from psycopg import errors as pg_errors

    async def slow(*a, **k):
        raise pg_errors.QueryCanceled("canceling statement due to statement timeout")

    monkeypatch.setattr("app.routers.patients.fetch_all", slow)
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        r = c.get("/v1/patients", headers=auth(identities, "nurse"))
    assert r.status_code == 503 and "Retry-After" in r.headers
    assert "statement" not in r.text.lower() and "canceling" not in r.text.lower()


# --------------------------------------------------------------------------- T2600 result-set size
@pytest.mark.parametrize("path", ["/v1/patients", "/v1/alarms", "/v1/events", "/v1/staff"])
def test_t2600_oversized_limit_rejected_and_default_sql_is_limited(client, identities, fake_db, path):
    h = auth(identities, "admin")
    assert client.get(path, params={"limit": 1000}, headers=h).status_code == 422
    assert fake_db.calls == []
    r = client.get(path, headers=h)
    assert r.status_code == 200
    assert any(re.search(r"\blimit\b", sql, re.I) for _, sql, _ in fake_db.calls), fake_db.calls


def test_t2600_audit_report_over_max_rows_is_422_result_too_large(client, identities, fake_db, monkeypatch):
    from app.services import reports

    monkeypatch.setattr(reports, "MAX_AUDIT_ROWS", 3)
    captured = {}

    async def rows(conn, sql, params=()):
        captured.update(params)
        return [{"id": i} for i in range(params["limit"])]  # the database honours LIMIT max+1

    monkeypatch.setattr(reports, "fetch_all", rows)
    fake_db.one = {"retry_after": 0, "broken_at": None}
    r = client.get("/v1/reports/audit", headers=auth(identities, "admin"))
    assert r.status_code == 422 and r.json().get("code") == "result_too_large", r.text
    assert captured["limit"] == 4  # limit + 1, never silently truncated
    r = client.get("/v1/reports/export.csv", params={"kind": "audit_events"}, headers=auth(identities, "admin"))
    assert r.status_code == 422 and r.json().get("code") == "result_too_large"


def test_t2600_supabase_api_max_rows_is_explicit():
    from pathlib import Path

    toml = (Path(__file__).resolve().parents[2] / "supabase" / "config.toml").read_text(encoding="utf-8")
    m = re.search(r"^max_rows\s*=\s*(\d+)", toml.split("[api]", 1)[1].split("\n[", 1)[0], re.M)
    assert m and 1 <= int(m.group(1)) <= 1000


# --------------------------------------------------------------------------- T29 CSRF (bearer-token design + Origin check)
SPA = "https://acme-clinical.vercel.app"


def test_t29_forged_cross_site_requests_are_refused(client, identities, fake_db):
    h = auth(identities, "nurse")
    path = f"/v1/alarms/{uuid.uuid4()}/acknowledge"
    r = client.post(path, content=b"acknowledged=true", headers={**h, "Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415
    r = client.post(path, json={"acknowledged": True}, headers={**h, "Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post(path, json={"acknowledged": True}, headers={"Origin": "null", **h})
    assert r.status_code == 403
    r = client.post(path, json={"acknowledged": True}, cookies={"sb-access-token": make_token(), "session": "x"})
    assert r.status_code == 401
    assert fake_db.calls == []


def test_t29_same_origin_and_non_browser_writes_still_work(client, identities, fake_db):
    fake_db.one = lambda sql, p: ({"id": str(uuid.uuid4()), "body": "x", "created_at": "2026-01-01T00:00:00Z"}
                                  if sql.lstrip().startswith("insert") else {"full_name": "N", "?column?": 1})
    h = auth(identities, "nurse")
    assert client.post(f"/v1/patients/{PID}/observations", json={"body": "x"}, headers={**h, "Origin": SPA}).status_code == 201
    assert client.post(f"/v1/patients/{PID}/observations", json={"body": "x"}, headers=h).status_code == 201
    assert client.get("/v1/health", headers={"Origin": "https://evil.example"}).status_code == 200  # reads: CORS decides


def test_t29_api_sets_no_cookies_so_no_ambient_credentials_exist(client, identities, fake_db):
    for r in (client.get("/v1/health"), client.post("/v1/auth/logout", headers=auth(identities, "nurse")),
              client.get("/v1/patients", headers=auth(identities, "nurse"))):
        assert "set-cookie" not in r.headers


# --------------------------------------------------------------------------- T66 framing
@pytest.mark.parametrize("method,path,extra", [("GET", "/v1/health", {}), ("GET", "/v1/nope", {}),
                                                ("DELETE", "/v1/health", {}), ("GET", "/v1/patients", {})])
def test_t66_every_response_forbids_framing(client, method, path, extra):
    r = client.request(method, path, **extra)
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_t66_rate_limited_and_oversized_responses_forbid_framing(client):
    statuses = set()
    for _ in range(40):
        r = client.get("/v1/patients")
        statuses.add(r.status_code)
        assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert 429 in statuses
    r = client.get("/v1/patients?q=" + "a" * 3000)
    assert r.status_code == 414 and r.headers["x-frame-options"] == "DENY"


# --------------------------------------------------------------------------- T257 CORS
@pytest.mark.parametrize("origin", ["https://evil.vercel.app", "null", "https://acme-clinical.vercel.app.evil.example",
                                    "http://acme-clinical.vercel.app"])
def test_t257_untrusted_origins_get_no_cors_grant(client, origin):
    r = client.options("/v1/patients", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
    r = client.get("/v1/health", headers={"Origin": origin})
    assert "access-control-allow-origin" not in r.headers


def test_t257_configured_origin_gets_exact_grant_without_credentials(client):
    r = client.options("/v1/patients", headers={"Origin": SPA, "Access-Control-Request-Method": "GET",
                                                "Access-Control-Request-Headers": "authorization"})
    assert r.headers["access-control-allow-origin"] == SPA
    assert r.headers["access-control-max-age"] == "600"
    assert "access-control-allow-credentials" not in r.headers
    r = client.get("/v1/health", headers={"Origin": SPA})
    assert r.headers["access-control-allow-origin"] == SPA and r.headers.get("access-control-allow-credentials") != "true"


@pytest.mark.parametrize("value", ["*", "https://*.vercel.app", "https://.*\.vercel\.app", "https://acme.vercel.app/app",
                                   "https://acme.vercel.app/?x=1", "https://user:pw@acme.vercel.app"])
def test_t257_settings_refuse_wildcard_regex_or_non_origin_values(monkeypatch, value):
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", value)
    with pytest.raises(ValidationError):
        Settings()
