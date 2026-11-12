"""Input-validation security tests (skills/input-validation countermeasures).

The database is not available in tests: ``fake_db`` replaces the routers' ``transaction`` /
``fetch_*`` helpers with an in-memory recorder, so tests can assert both the HTTP behaviour and the
exact SQL text + bound parameters that would have been sent to PostgreSQL.
"""

from __future__ import annotations

import ast
import json
import re
import socket
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.responses import Response

from app.core import middleware, validation
from app.core.config import Settings, get_settings
from app.main import create_app
from app.schemas import ObservationIn, ProfileUpdate, StaffInvite, ThresholdUpdate
from tests.conftest import add_identity, make_token

BACKEND = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND / "app"
REPO = BACKEND.parent
PID = "00000000-0000-4000-8000-000000000001"
MID = "00000000-0000-4000-8000-000000000002"
ROUTER_MODULES = ("alarms", "auth", "break_glass", "events", "files", "maintenance", "monitors", "observations",
                  "patients", "profile", "reports", "settings", "simulation", "staff", "thresholds", "wards")


# --------------------------------------------------------------------------- helpers / fixtures
class FakeConn:
    def __init__(self, db: FakeDB):
        self.db = db

    async def execute(self, sql, params=()):
        self.db.calls.append(("execute", sql, params))


class FakeDB:
    """Records every statement; ``rows`` feeds fetch_all, ``one`` (value or callable) feeds fetch_one."""

    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []
        self.rows: list[dict] = []
        self.one = None

    @asynccontextmanager
    async def transaction(self, principal):
        yield FakeConn(self)

    async def fetch_all(self, conn, sql, params=()):
        self.calls.append(("all", sql, params))
        return list(self.rows)

    async def fetch_one(self, conn, sql, params=()):
        self.calls.append(("one", sql, params))
        return self.one(sql, params) if callable(self.one) else self.one

    @property
    def sql(self) -> list[str]:
        return [c[1] for c in self.calls]


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    import importlib

    for name in ROUTER_MODULES:
        module = importlib.import_module(f"app.routers.{name}")
        for attr in ("transaction", "fetch_all", "fetch_one"):
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, getattr(db, attr))
    monkeypatch.setattr("app.db.transaction", db.transaction)
    return db


def auth(identities, role: str) -> dict[str, str]:
    uid = add_identity(identities, role)
    token = make_token(uid, aal="aal2" if role == "admin" else "aal1", auth_time=int(time.time()))
    return {"Authorization": f"Bearer {token}"}


def py_files(root: Path = APP_DIR):
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


LEAKS = ("syntax error", "psycopg", "sqlstate", "postgres", "traceback", "select ", "relation ")


# --------------------------------------------------------------------------- T101 SQL injection
_SQL_TEXT = re.compile(r"\b(select|insert|update|delete)\b.*\b(from|into|set|where|returning)\b", re.I | re.S)


def _literal_names(tree: ast.AST) -> set[str]:
    """Names that are only ever assigned plain string literals (fixed SQL fragments / identifiers)."""
    literal, other = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            for t in targets:
                if isinstance(t, ast.Name):
                    is_lit = isinstance(value, ast.Constant) and isinstance(value.value, str)
                    (literal if is_lit else other).add(t.id)
    return literal - other


# Interpolated identifiers that were reviewed: (file, variable) -> (allow-list constant, required filter text).
VERIFIED_IDENTIFIER_INTERPOLATIONS = {
    ("settings.py", "column"): ("_COLUMNS", "if k in _COLUMNS"),
}


def test_t101_verified_identifier_allow_lists_are_fixed_literals():
    for (filename, _var), (const, guard) in VERIFIED_IDENTIFIER_INTERPOLATIONS.items():
        path = next(p for p in py_files() if p.name == filename)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assigned = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == const for t in n.targets)]
        assert len(assigned) == 1 and isinstance(assigned[0], ast.Tuple), (filename, const)
        assert all(isinstance(e, ast.Constant) and re.fullmatch(r"[a-z_]+", e.value) for e in assigned[0].elts)
        assert guard in source, (filename, guard)  # interpolated values are filtered through the allow-list


def test_t101_no_string_built_sql_in_backend():
    """Static check: SQL is never built with f-strings, % formatting or .format() from variable data."""
    offenders = []
    for path in py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fixed = _literal_names(tree) | {var for (f, var) in VERIFIED_IDENTIFIER_INTERPOLATIONS if f == path.name}
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                text = "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
                if _SQL_TEXT.search(text):
                    for v in node.values:
                        if isinstance(v, ast.FormattedValue) and not (isinstance(v.value, ast.Name) and v.value.id in fixed):
                            offenders.append(f"{path.name}:{node.lineno} f-string SQL interpolates {ast.unparse(v.value)}")
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) \
                    and isinstance(node.left.value, str) and _SQL_TEXT.search(node.left.value):
                offenders.append(f"{path.name}:{node.lineno} %-formatted SQL")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format" \
                    and isinstance(node.func.value, ast.Constant) and _SQL_TEXT.search(str(node.func.value.value)):
                offenders.append(f"{path.name}:{node.lineno} str.format SQL")
    assert offenders == []


SQLI_PAYLOADS = ["'", "1'", "' OR '1'='1", "'; DROP TABLE patients;--", '") OR 1=1--', "1 UNION SELECT null--", "/* */"]


@pytest.mark.parametrize("payload", SQLI_PAYLOADS)
def test_t101_patient_search_payload_is_only_a_bound_parameter(client, identities, fake_db, payload):
    h = auth(identities, "nurse")
    baseline = client.get("/v1/patients", params={"q": "zzz-no-match"}, headers=h)
    r = client.get("/v1/patients", params={"q": payload}, headers=h)
    assert baseline.status_code == 200 and r.status_code in (200, 422)
    assert not any(leak in r.text.lower() for leak in LEAKS)
    if r.status_code == 200:
        assert len(r.json()["items"]) == len(baseline.json()["items"])
        sql, params = fake_db.calls[-1][1], fake_db.calls[-1][2]
        assert sql == fake_db.calls[0][1]  # identical statement text: the payload never reaches the SQL
        assert any(payload.replace("%", "\\%").replace("_", "\\_") in str(v) for v in params.values())


@pytest.mark.parametrize("path,param", [("/v1/alarms", "state"), ("/v1/events", "action"), ("/v1/events", "entity_type"),
                                        ("/v1/thresholds", "ward_id"), ("/v1/patients", "ward_id")])
@pytest.mark.parametrize("payload", SQLI_PAYLOADS[:4])
def test_t101_filters_reject_sql_metacharacters(client, identities, fake_db, path, param, payload):
    r = client.get(path, params={param: payload}, headers=auth(identities, "admin"))
    assert r.status_code == 422
    assert not any(leak in r.text.lower() for leak in LEAKS)
    assert fake_db.calls == []


# --------------------------------------------------------------------------- T569 / T577 parameter tampering
def _request_schemas(app) -> dict[str, dict]:
    spec = app.openapi()
    comps = spec["components"]["schemas"]
    names = set()
    for ops in spec["paths"].values():
        for op in ops.values():
            ref = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref")
            if ref:
                names.add(ref.rsplit("/", 1)[-1])
    return {n: comps[n] for n in names}


def _walk(schema: dict, path: str, problems: list[str]) -> None:
    if "$ref" in schema:
        return
    for key in ("anyOf", "allOf", "oneOf"):
        for i, sub in enumerate(schema.get(key, [])):
            _walk(sub, f"{path}[{i}]", problems)
    if any(k in schema for k in ("anyOf", "allOf", "oneOf")):
        return
    t = schema.get("type")
    if not t and "enum" not in schema and "const" not in schema:
        problems.append(f"untyped {path}")
    if t == "object":
        if schema.get("additionalProperties") is not False:
            problems.append(f"open object {path}")
        for k, v in schema.get("properties", {}).items():
            _walk(v, f"{path}.{k}", problems)
    if t == "string" and "enum" not in schema and "format" not in schema and "maxLength" not in schema:
        problems.append(f"unbounded string {path}")
    if t in ("integer", "number") and ("maximum" not in schema or "minimum" not in schema):
        problems.append(f"unbounded number {path}")
    if t == "array":
        if "maxItems" not in schema:
            problems.append(f"unbounded array {path}")
        _walk(schema.get("items", {}), f"{path}[]", problems)


def test_t577_request_schemas_are_typed_bounded_and_closed():
    app = create_app()
    schemas = _request_schemas(app)
    assert {"ObservationIn", "ThresholdUpdate", "AssignMonitor", "MaintenanceIn", "StaffInvite"} <= set(schemas)
    problems: list[str] = []
    for name, schema in schemas.items():
        _walk(schema, name, problems)
    assert problems == []


def test_t569_enumerations_are_enums_in_openapi():
    comps = create_app().openapi()["components"]["schemas"]
    for name in ("RoleName", "Scenario", "VitalParameter", "MaintenanceKind"):
        assert comps[name].get("enum"), name


WRITE_CASES = [
    ("put", f"/v1/thresholds/wards/{PID}", "physician", {"parameter": "spo2", "low_limit": "90", "high_limit": 100, "confirm": True}),
    ("put", f"/v1/thresholds/wards/{PID}", "physician", {"parameter": "spo2", "low_limit": 90.5, "high_limit": 100, "confirm": True}),
    ("put", f"/v1/thresholds/wards/{PID}", "physician", {"parameter": "glucose", "low_limit": 1, "high_limit": 2, "confirm": True}),
    ("put", f"/v1/thresholds/wards/{PID}", "physician", {"parameter": "spo2", "low_limit": 90, "high_limit": 100, "confirm": "yes"}),
    ("put", f"/v1/thresholds/patients/{PID}", "physician",
     {"parameter": "spo2", "low_limit": 90, "high_limit": 100, "confirm": True, "updated_by": str(uuid.uuid4())}),
    ("post", f"/v1/patients/{PID}/observations", "nurse", {"body": "ok", "author_id": str(uuid.uuid4())}),
    ("post", f"/v1/patients/{PID}/observations", "nurse", {"body": 123}),
    ("post", f"/v1/monitors/{MID}/assignment", "biomed_tech", {"bed_id": "not-a-uuid", "confirm": True}),
    ("post", f"/v1/monitors/{MID}/assignment", "biomed_tech", {"bed_id": PID, "confirm": True, "assigned_by": PID}),
    ("post", f"/v1/monitors/{MID}/maintenance", "biomed_tech", {"kind": "teleport"}),
    ("post", f"/v1/monitors/{MID}/maintenance", "biomed_tech", {"kind": "repair", "performed_by": PID}),
    ("post", f"/v1/alarms/{PID}/acknowledge", "nurse", {"note": "ok", "acknowledged_by": str(uuid.uuid4())}),
    ("patch", "/v1/me", "nurse", {"full_name": "Nurse", "role": "admin"}),
    ("post", "/v1/staff", "admin", {"email": "a@acme-clinical.org", "full_name": "A B", "role": "superuser"}),
    ("patch", "/v1/settings/security", "admin", {"session_idle_minutes": "15"}),
    ("post", "/v1/simulation/scenario", "admin", {"scenario": "explode"}),
    ("post", "/v1/simulation/advance", "admin", {"steps": -5, "expected_version": 1}),
    ("post", "/v1/simulation/advance", "admin", {"steps": True, "expected_version": 1}),
    ("post", "/v1/break-glass", "nurse", {"patient_id": PID, "reason": "emergency access needed", "expires_at": "2099-01-01"}),
]


@pytest.mark.parametrize("method,path,role,body", WRITE_CASES)
def test_t577_t98_tampered_requests_rejected_server_side(client, identities, fake_db, method, path, role, body):
    r = getattr(client, method)(path, json=body, headers=auth(identities, role))
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "Invalid request."
    assert not any(kind == "execute" or "insert" in sql or "update" in sql for kind, sql, _ in fake_db.calls)


# --------------------------------------------------------------------------- T33 / T99 read-only data
def test_t33_no_request_model_carries_server_owned_fields():
    forbidden = {"author_id", "acknowledged_by", "acknowledged_at", "role_claim", "severity", "priority", "performed_by",
                 "assigned_by", "updated_by", "created_at", "user_id", "actor_id"}
    for name, schema in _request_schemas(create_app()).items():
        assert not forbidden & set(schema.get("properties", {})), name


def test_t99_observation_author_comes_from_token(client, identities, fake_db):
    uid = add_identity(identities, "nurse")
    created = {"id": str(uuid.uuid4()), "body": "Stable", "created_at": "2026-01-01T00:00:00Z"}

    def one(sql, params):
        if sql.lstrip().startswith("insert"):
            return created
        if "full_name" in sql:
            return {"full_name": "Nurse Real"}
        return {"?column?": 1}

    fake_db.one = one
    r = client.post(f"/v1/patients/{PID}/observations", json={"body": "Stable"},
                    headers={"Authorization": f"Bearer {make_token(uid)}"})
    assert r.status_code == 201
    insert = next(c for c in fake_db.calls if c[1].lstrip().startswith("insert into public.observations"))
    assert insert[2] == (PID, uid, "Stable")
    assert r.json()["author_name"] == "Nurse Real"


def test_t99_profile_cannot_escalate_role(client, identities, fake_db):
    r = client.patch("/v1/me", json={"full_name": "Nurse", "role": "admin"}, headers=auth(identities, "nurse"))
    assert r.status_code == 422
    assert fake_db.calls == []


# --------------------------------------------------------------------------- T39 CRLF in response headers
@pytest.mark.parametrize("value", ["a\r\nSet-Cookie: x=1", "a%0d%0aSet-Cookie:x=1", "a%250A", "a%%0A0A", "a\nb", "a\x00"])
def test_t39_header_values_with_crlf_rejected(value):
    with pytest.raises(ValueError):
        validation.safe_header_value(value)


def test_t39_content_disposition_is_single_sanitised_header():
    value = validation.content_disposition('Jane\r\nSet-Cookie: x=1 "report".pdf')
    assert "\r" not in value and "\n" not in value and '"report"' not in value
    response = Response(b"%PDF-", media_type="application/pdf", headers={"Content-Disposition": value})
    names = [k for k, _ in response.raw_headers]
    assert names.count(b"content-disposition") == 1 and b"set-cookie" not in names
    assert validation.safe_header_value("report-2026.pdf") == "report-2026.pdf"


def test_t39_api_never_puts_request_data_in_headers(client):
    r = client.get("/v1/health", headers={"X-Request-Id": "abc\r\nSet-Cookie: x=1"})
    assert "set-cookie" not in r.headers and "\n" not in r.headers["x-request-id"]


# --------------------------------------------------------------------------- T127 null bytes
@pytest.mark.parametrize("text", ["ok\x00DROP", "a\u0000.pdf"])
def test_t127_text_with_nul_returns_422_not_500(client, identities, fake_db, text):
    r = client.post(f"/v1/patients/{PID}/observations", json={"body": text}, headers=auth(identities, "nurse"))
    assert r.status_code == 422
    assert fake_db.calls == []


@pytest.mark.parametrize("q", ["x%00.pdf", "x\x00"])
def test_t127_query_with_nul_rejected(client, identities, fake_db, q):
    r = client.get("/v1/patients", params={"q": q.replace("%00", "\x00")}, headers=auth(identities, "nurse"))
    assert r.status_code == 422


@pytest.mark.parametrize("name", ["report%00.pdf", "../../etc/passwd\x00.pdf", "a\x00.pdf", "..\\..\\x.pdf"])
def test_t127_file_names_never_keep_nul_or_path_segments(name):
    safe = validation.safe_filename(name)
    assert "\x00" not in safe and "/" not in safe and "\\" not in safe and ".." not in safe.split(".pdf")[0][:2]


# --------------------------------------------------------------------------- T31 / T32 / T98 / T34 server-side validation
@pytest.mark.parametrize("body", [
    {"parameter": "heart_rate", "low_limit": 300, "high_limit": 301, "confirm": True},
    {"parameter": "spo2", "low_limit": -1, "high_limit": 100, "confirm": True},
    {"parameter": "heart_rate", "low_limit": 120, "high_limit": 60, "confirm": True},
    {"parameter": "heart_rate", "low_limit": 60, "high_limit": 120, "confirm": False},
])
def test_t31_threshold_ranges_and_consistency(body):
    with pytest.raises(ValidationError):
        ThresholdUpdate(**body)


def test_t31_valid_threshold_accepted():
    assert ThresholdUpdate(parameter="heart_rate", low_limit=50, high_limit=120, confirm=True).low_limit == 50


def test_t32_validation_failures_are_logged_without_values(client, identities, fake_db, monkeypatch):
    logged: list[tuple[str, dict]] = []
    monkeypatch.setattr(middleware.security_log, "warning", lambda msg, extra=None: logged.append((msg, extra or {})))
    r = client.post("/v1/staff", json={"full_name": "A" * 500, "email": "x", "role": "root"}, headers=auth(identities, "admin"))
    assert r.status_code == 422 and r.json()["error"] == "Invalid request."
    assert "AAAA" not in r.text
    msg, extra = logged[-1]
    assert msg == "request_rejected" and extra["route"] == "/v1/staff" and extra["code"] == "VALIDATION_422"
    assert extra["client_ip"] and extra["request_id"]
    assert "AAAA" not in json.dumps(extra)


@pytest.mark.parametrize("text", ["bad\x00", "rtl‮override", "zero​width", "c1\x85", "x" * 2001, "\ud800"])
def test_t34_observation_rejects_control_bidi_and_overlong(text):
    with pytest.raises(ValidationError):
        ObservationIn(body=text)


def test_t34_multiline_observation_accepted(client, identities, fake_db):
    fake_db.one = lambda sql, p: ({"id": str(uuid.uuid4()), "body": p[2], "created_at": "2026-01-01T00:00:00Z"}
                                  if sql.lstrip().startswith("insert") else {"full_name": "N", "?column?": 1})
    r = client.post(f"/v1/patients/{PID}/observations", json={"body": "Line 1\nLine 2\tvalue"}, headers=auth(identities, "nurse"))
    assert r.status_code == 201 and r.json()["body"] == "Line 1\nLine 2\tvalue"


@pytest.mark.parametrize("name", ["Jane\tDoe", "Jane\nDoe", "Jane Doe", "Jane  Doe", "<script>", "Robert'); DROP--", "1234"])
def test_t34_single_line_names_rejected(name):
    with pytest.raises(ValidationError):
        ProfileUpdate(full_name=name)


def test_t34_invalid_utf8_body_is_4xx(client, identities, fake_db):
    r = client.post(f"/v1/patients/{PID}/observations", content=b'{"body": "\xff\xfe"}',
                    headers={**auth(identities, "nurse"), "Content-Type": "application/json"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- T519 every input validated
def _param_cases():
    spec = create_app().openapi()
    bad = {"string": ["\x00", "‮"], "integer": ["-1", "x", "1.5"], "boolean": ["maybe"], "uuid": ["1 OR 1=1", "not-a-uuid"]}
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            for p in op.get("parameters", []):
                schema = p["schema"].get("anyOf", [p["schema"]])[0]
                kind = "uuid" if schema.get("format") == "uuid" else schema.get("type")
                if schema.get("enum") and kind == "string":
                    kind = "uuid"  # enum: any non-member is invalid
                for value in bad.get(kind, []):
                    yield method, path, p["name"], p["in"], value


@pytest.mark.parametrize("method,path,name,where,value", list(_param_cases()))
def test_t519_every_parameter_rejects_invalid_values(client, identities, fake_db, method, path, name, where, value):
    url = path
    for placeholder in re.findall(r"{(\w+)}", path):
        url = url.replace("{" + placeholder + "}", value if (where == "path" and placeholder == name) else PID)
    params = {name: value} if where == "query" else None
    for role in ("physician", "biomed_tech", "admin", "nurse"):
        r = client.request(method.upper(), url, params=params, headers=auth(identities, role),
                           json={} if method in ("post", "put", "patch") else None)
        if r.status_code != 403:
            break
    assert r.status_code in (400, 403, 404, 405, 422), (method, path, name, value, r.status_code)


# --------------------------------------------------------------------------- T74 HTTP parameter pollution
def test_t74_duplicate_single_valued_params_rejected(client, identities, fake_db):
    h = auth(identities, "nurse")
    assert client.get("/v1/patients?q=a&q=b", headers=h).status_code == 400
    assert client.get("/v1/patients?q=%3Cscr&q=ipt%3E", headers=h).status_code == 400
    assert client.get(f"/v1/patients?ward_id={PID}&ward_id={MID}", headers=h).status_code == 400
    assert fake_db.calls == []
    assert client.get("/v1/patients?q=a&limit=10", headers=h).status_code == 200


# --------------------------------------------------------------------------- T1148 / T1149 JSON validation
MALICIOUS_JSON = [
    b'{"scenario": "low_saturation"',                               # truncated
    b'{"scenario": ["low_saturation"]}',                            # type confusion
    b'{"scenario": "normal", "__proto__": {"admin": true}}',      # unknown key
    b'{"a":' * 5000 + b"1" + b"}" * 5000,                           # nesting bomb
    b'{"scenario": "normal", "scenario": "low_battery"}',          # duplicate keys
    b'["normal"]',                                                  # non-object body
    b'"normal"',
    b'{"steps": NaN, "expected_version": 1}',
    b'{"scenario": "\xff"}',                                        # invalid UTF-8
]


@pytest.mark.parametrize("raw", MALICIOUS_JSON)
def test_t1149_simulation_rejects_malicious_json(client, identities, fake_db, raw):
    r = client.post("/v1/simulation/scenario", content=raw, headers={**auth(identities, "admin"), "Content-Type": "application/json"})
    assert r.status_code in (400, 413, 422)
    assert fake_db.calls == []


def test_t1148_json_bodies_require_json_content_type(client, identities, fake_db):
    r = client.post(f"/v1/patients/{PID}/observations", content=b'{"body": "x"}',
                    headers={**auth(identities, "nurse"), "Content-Type": "text/plain"})
    assert r.status_code == 415


@pytest.mark.parametrize("raw,ok", [(b'{"a": {"b": [1, 2]}}', True), (b'{"a": 1, "a": 2}', False), (b"[]", False),
                                    (b'{"a": Infinity}', False), (b'{"a": "' + b"[" * 50 + b'"}', True),
                                    (b"[" * 9 + b"]" * 9, False)])
def test_t1148_parse_json_object(raw, ok):
    if ok:
        assert isinstance(validation.parse_json_object(raw), dict)
    else:
        with pytest.raises(validation.JsonStructureError):
            validation.parse_json_object(raw)


def test_t1148_no_json_built_with_string_templates():
    for path in py_files():
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"""f["']\s*\{\s*\\?["']""", source), path  # f'{"key": ...}' style JSON literals


# --------------------------------------------------------------------------- T420 / T421 / T89 / T169 XSS & CSTI (API side)
XSS = ["<script>alert('xss')</script>", "\"><img src=x onerror=alert(1)>", "{{constructor.constructor('alert(1)')()}}",
       "${7*7}", "javascript:alert(1)"]


@pytest.mark.parametrize("payload", XSS)
def test_t89_reflected_input_is_never_html(client, identities, fake_db, payload):
    r = client.get("/v1/patients", params={"q": payload * 3}, headers=auth(identities, "nurse"))
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert payload not in r.text  # 422 never echoes values; 200 returns only stored data


@pytest.mark.parametrize("payload", XSS)
def test_t420_stored_payload_returned_as_inert_json_text(client, identities, fake_db, payload):
    fake_db.one = lambda sql, p: ({"id": str(uuid.uuid4()), "body": p[2], "created_at": "2026-01-01T00:00:00Z"}
                                  if sql.lstrip().startswith("insert") else {"full_name": "N", "?column?": 1})
    r = client.post(f"/v1/patients/{PID}/observations", json={"body": payload}, headers=auth(identities, "nurse"))
    assert r.status_code == 201
    assert r.headers["content-type"] == "application/json"
    assert r.json()["body"] == payload  # stored verbatim, never evaluated; the SPA renders it as text


def test_t169_api_returns_no_html_or_script_sinks():
    for path in py_files():
        source = path.read_text(encoding="utf-8")
        for sink in ("HTMLResponse", 'media_type="text/html', "innerHTML", "dangerouslySetInnerHTML", "render_template"):
            assert sink not in source, (path.name, sink)


# --------------------------------------------------------------------------- T1145 SSTI / T122 file include
def test_t1145_no_server_side_template_engine_on_user_data():
    for path in py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                assert not any(m.split(".")[0] in ("jinja2", "mako", "chameleon", "string") and
                               (m != "string" or any(a.name == "Template" for a in node.names)) for m in mods), path.name
            if isinstance(node, ast.Call):
                attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
                bare = node.func.id if isinstance(node.func, ast.Name) else None
                assert attr not in ("from_string", "render_template_string", "Template"), f"{path.name}:{node.lineno} {attr}"
                assert bare not in ("Template", "eval", "exec", "compile"), f"{path.name}:{node.lineno} {bare}"


SSI = ['<!--#include virtual="/etc/passwd" -->', '<!--#exec cmd="id" -->', "{% include '/etc/passwd' %}",
       "{{'5'*5}}", "http://attacker.example/x.txt", "../../app/core/config.py"]


@pytest.mark.parametrize("payload", SSI)
def test_t122_t1145_include_and_template_payloads_stay_inert(client, identities, fake_db, payload):
    fake_db.one = lambda sql, p: ({"id": str(uuid.uuid4()), "body": p[2], "created_at": "2026-01-01T00:00:00Z"}
                                  if sql.lstrip().startswith("insert") else {"full_name": "N", "?column?": 1})
    r = client.post(f"/v1/patients/{PID}/observations", json={"body": payload}, headers=auth(identities, "nurse"))
    assert r.status_code == 201
    assert r.json()["body"] == payload
    assert "root:x:" not in r.text and "uid=" not in r.text and "55555" not in r.text and "SUPABASE" not in r.text


def test_t122_scenario_is_enum_not_a_path_or_url(client, identities, fake_db):
    for scenario in ("http://attacker.example/s.json", "../../etc/passwd", "normal.json"):
        r = client.post("/v1/simulation/scenario", json={"scenario": scenario}, headers=auth(identities, "admin"))
        assert r.status_code == 422


def test_t122_no_file_access_from_request_handlers():
    """Handlers never open, include or execute files by name (server-generated temp files via os.open are allowed)."""
    for path in py_files(APP_DIR / "routers") + py_files(APP_DIR / "services"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        builtin_open = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id in ("open", "__import__", "exec", "eval")]
        assert builtin_open == [], (path.name, builtin_open)
        for call in ("read_text(", "read_bytes(", "importlib", "subprocess", "os.system", "Path(request", "open(request"):
            assert call not in source, (path.name, call)


# --------------------------------------------------------------------------- T1392 SSRF
def test_t1392_outbound_http_only_to_configured_supabase():
    for path in py_files():
        source = path.read_text(encoding="utf-8")
        assert "import requests" not in source and "urllib.request" not in source and "aiohttp" not in source, path.name
        for match in re.finditer(r"httpx\.AsyncClient\(\s*base_url=([^,\n]+)", source):
            expr = match.group(1)
            if re.fullmatch(r"\w+", expr):  # a local variable: it must be assigned from the configured Supabase URL
                assert re.search(rf"\b{expr}\s*=\s*str\([^\n]*supabase_url", source), (path.name, match.group(0))
            else:
                assert "supabase_url" in expr, (path.name, match.group(0))
        # every client is pinned to a base_url (no absolute URLs from elsewhere)
        assert source.count("httpx.AsyncClient(") == len(re.findall(r"httpx\.AsyncClient\(\s*base_url=", source)), path.name
        for match in re.finditer(r"client\.(?:get|post|put|patch|delete|request\(\s*[\"'][A-Z]+[\"']\s*,)\(?\s*f?[\"']([^\"']*)",
                                 source):
            assert match.group(1).startswith("/"), (path.name, match.group(0))  # relative to the fixed base_url


def test_t1392_no_request_field_accepts_a_url():
    for name, schema in _request_schemas(create_app()).items():
        for field, spec in schema.get("properties", {}).items():
            assert not re.search(r"(url|uri|href|host|endpoint|callback|webhook)", field, re.I), (name, field)
            assert spec.get("format") not in ("uri", "url"), (name, field)


SSRF = ["http://127.0.0.1:80", "http://169.254.169.254/latest/meta-data/", "file:///etc/passwd", "gopher://127.0.0.1:6379/_INFO",
        "http://[::1]/", "http://0x7f000001/"]


@pytest.mark.parametrize("payload", SSRF)
@pytest.mark.parametrize("method,path,role,field", [("patch", "/v1/me", "nurse", "avatar_url"),
                                                     ("post", f"/v1/monitors/{MID}/maintenance", "biomed_tech", "callback_url"),
                                                     ("post", "/v1/simulation/scenario", "admin", "integration_url")])
def test_t1392_url_payloads_cause_no_outbound_connection(client, identities, fake_db, monkeypatch, method, path, role, field, payload):
    attempts: list[object] = []
    monkeypatch.setattr(socket.socket, "connect", lambda self, addr: attempts.append(addr))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: attempts.append(a))
    r = getattr(client, method)(path, json={field: payload}, headers=auth(identities, role))
    assert r.status_code == 422
    assert attempts == []


# --------------------------------------------------------------------------- T125 / T11 open redirect (API side)
def test_t11_backend_never_issues_redirects():
    for path in py_files():
        source = path.read_text(encoding="utf-8")
        assert "RedirectResponse" not in source and '"Location"' not in source and "'location'" not in source.lower(), path.name


@pytest.mark.parametrize("target", ["https://www.google.com", "//evil.example", "/\\evil.example", "javascript:alert(1)"])
def test_t125_next_parameters_do_not_redirect(client, identities, fake_db, target):
    for url in ("/v1/health", "/v1/patients"):
        r = client.get(url, params={"next": target, "redirect": target}, headers=auth(identities, "nurse"),
                       follow_redirects=False)
        assert not 300 <= r.status_code < 400 and "location" not in r.headers


# --------------------------------------------------------------------------- T599 / T600 mutable headers
def test_t599_untrusted_host_rejected(client):
    assert client.get("/v1/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/v1/health", headers={"Host": "vercel.app.evil.example"}).status_code == 400
    assert client.get("/v1/health", headers={"Host": "acme-clinical-api.vercel.app"}).status_code == 200


def test_t599_no_host_or_referer_in_links_or_decisions():
    for path in py_files():
        source = path.read_text(encoding="utf-8")
        if path.name == "middleware.py":  # the Host allow-list validator itself reads Host only to reject it
            source = source.replace('request.headers.get("host", "")', "")
        for pattern in (r"request\.base_url", r"url_for\(", r"headers\.get\(\s*[\"'](host|referer|origin|x-forwarded-host)[\"']",
                        r"headers\[\s*[\"'](host|referer|origin|x-forwarded-host)[\"']"):
            assert not re.search(pattern, source, re.I), (path.name, pattern)


def test_t600_referer_is_not_authentication(client, fake_db):
    for referer in ("https://acme-clinical.vercel.app/simulation", "https://acme-clinical.vercel.app"):
        r = client.post("/v1/simulation/reset", json={"confirm_text": "RESET DEMO DATA"},
                        headers={"Referer": referer, "Origin": "https://acme-clinical.vercel.app"})
        assert r.status_code == 401
    assert fake_db.calls == []


def test_t600_forwarded_and_agent_headers_not_reflected(client, identities, fake_db):
    r = client.get("/v1/patients", headers={**auth(identities, "nurse"), "X-Forwarded-Host": "evil.example",
                                            "User-Agent": "<script>x</script>"})
    assert r.status_code == 200 and "evil.example" not in r.text and "<script>" not in r.text
    assert "evil.example" not in "".join(r.headers.values())


# --------------------------------------------------------------------------- T1038 / T1039 homoglyphs
@pytest.mark.parametrize("regular,lookalike", [("Admin Smith", "Аdmin Smith"), ("Paul Moore", "Pаul Moore"),
                                               ("Ana Costa", "Αna Costa")])
def test_t1039_lookalike_names_rejected(regular, lookalike):
    assert ProfileUpdate(full_name=regular).full_name == regular
    with pytest.raises(ValidationError):
        ProfileUpdate(full_name=lookalike)


@pytest.mark.parametrize("name", ["José da Silva", "Zoë O'Neil", "Иван Петров", "Mary-Jane Watson", "Dr. Ana Lúcia"])
def test_t1038_single_script_names_accepted(name):
    assert ProfileUpdate(full_name=name).full_name


def test_t1038_combining_marks_and_fullwidth_normalised_or_rejected():
    with pytest.raises(ValidationError):
        ProfileUpdate(full_name="Bed̵ Nurse")
    assert ProfileUpdate(full_name="Ｎｕｒｓｅ").full_name == "Nurse"  # full-width -> NFKC


def test_t1039_staff_invite_rejects_homoglyph_name_and_idn_email(client, identities, fake_db):
    h = auth(identities, "admin")
    r1 = client.post("/v1/staff", json={"email": "a@acme-clinical.org", "full_name": "Аdmin Smith", "role": "nurse"}, headers=h)
    r2 = client.post("/v1/staff", json={"email": "nurse@аcme-clinical.org", "full_name": "Nurse One", "role": "nurse"}, headers=h)
    assert r1.status_code == 422 and r2.status_code == 422
    with pytest.raises(ValidationError):
        StaffInvite(email="nurse@xn--cme-8cd.test́", full_name="Nurse", role="nurse")
    assert StaffInvite(email="Nurse@Acme-Clinical.org", full_name="Nurse One", role="nurse").email == "nurse@acme-clinical.org"


def test_t1038_ascii_identifier():
    assert validation.ascii_identifier("BED-01") == "BED-01"
    for bad in ("BED-0١", "BED​01", "ВED-01"):
        with pytest.raises(ValueError):
            validation.ascii_identifier(bad)


# --------------------------------------------------------------------------- T2608 connection string
_DSN = re.compile(r"postgres(?:ql)?://([^\s:'\"/@]+):([^\s'\"@]+)@")
_PLACEHOLDER = re.compile(r"^(<[^>]+>|\$\{?[A-Za-z_]+\}?|\[[^\]]+\]|\*+|password|your[-_a-z]*)$", re.I)


def test_t2608_no_hardcoded_connection_strings():
    offenders = []
    for root in (BACKEND, REPO / "supabase", REPO / "frontend"):
        for p in root.rglob("*"):
            if not p.is_file() or {"node_modules", "dist", "__pycache__", ".pytest_cache", "tests"} & set(p.parts):
                continue
            if p.suffix not in {".py", ".ts", ".tsx", ".js", ".json", ".sql", ".toml", ".example", ".yaml", ".yml", ".md"} \
                    and not p.name.startswith(".env"):
                continue
            for m in _DSN.finditer(p.read_text(encoding="utf-8", errors="ignore")):
                if not _PLACEHOLDER.match(m.group(2)):
                    offenders.append(f"{p.relative_to(REPO)}: {m.group(0)[:20]}...")
    assert offenders == []


def test_t2608_dsn_only_from_settings_and_never_exposed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:SeCrEt@h:5432/d?sslmode=verify-full")
    s = Settings()
    assert "SeCrEt" not in repr(s) and "SeCrEt" not in str(s.model_dump())
    db_source = (APP_DIR / "db.py").read_text(encoding="utf-8")
    assert "conninfo=settings.database_url.get_secret_value()" in db_source
    for path in py_files():
        source = path.read_text(encoding="utf-8")
        if path.name != "db.py":
            assert "conninfo" not in source and "psycopg.connect(" not in source.replace("psycopg.connect(get_settings()", "") \
                or path.name == "cli.py", path.name


def test_t2608_settings_require_tls():
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://u:p@h/d")
    assert get_settings().database_url.get_secret_value().endswith("sslmode=verify-full")


# --------------------------------------------------------------------------- T2609 result-set size
OWNED_LIST_ENDPOINTS = ["/v1/patients", f"/v1/patients/{PID}/readings", f"/v1/patients/{PID}/observations", "/v1/thresholds",
                        "/v1/monitors", f"/v1/monitors/{MID}/maintenance"]


@pytest.mark.parametrize("path", OWNED_LIST_ENDPOINTS)
def test_t2609_list_endpoints_bound_result_size(client, identities, fake_db, path):
    role = "biomed_tech" if "/monitors" in path else "physician"
    h = auth(identities, role)
    fake_db.one = {"?column?": 1}
    assert client.get(path, params={"limit": 100000}, headers=h).status_code == 422
    assert client.get(path, params={"offset": 10**7}, headers=h).status_code in (200, 422)
    fake_db.rows = [{}] * 0
    r = client.get(path, headers=h)
    assert r.status_code == 200 and isinstance(r.json()["items"], list)
    limit_param = fake_db.calls[-1][2]
    values = list(limit_param.values()) if isinstance(limit_param, dict) else list(limit_param)
    assert any(isinstance(v, int) and 1 <= v <= 121 for v in values)
    assert re.search(r"\blimit\b", fake_db.calls[-1][1], re.I)


KNOWN_UNBOUNDED_ELSEWHERE = {"/v1/wards", "/v1/staff", "/v1/alarms/monitor-states", "/v1/break-glass/pending-review", "/v1/break-glass/mine"}  # see CROSS-OWNER requests


def test_t2609_every_collection_route_has_bounded_limit():
    app = create_app()
    spec = app.openapi()
    unbounded = set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or "GET" not in route.methods:
            continue
        model = route.response_model
        is_collection = model is not None and (getattr(model, "__origin__", None) is list or
                                               "items" in getattr(model, "model_fields", {}))
        if not is_collection:
            continue
        params = {p["name"]: p["schema"] for p in spec["paths"][route.path]["get"].get("parameters", [])}
        limit = params.get("limit")
        if not limit or limit.get("maximum", 10**9) > 120:
            if "{patient_id}/readings" in route.path or "/files/patients" in route.path:
                continue  # fixed server-side LIMIT (readings param max 120; files LIMIT 100)
            unbounded.add(route.path)
    assert unbounded <= KNOWN_UNBOUNDED_ELSEWHERE, unbounded
