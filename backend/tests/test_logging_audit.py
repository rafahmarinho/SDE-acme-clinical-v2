"""Logging & audit tests (skills/logging-audit): confidentiality of logs, security events, audit
completeness, signatures/non-repudiation, failure handling, protection, reports, errors, debug surface."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core import audit
from app.core import logging as app_logging
from app.core.config import Settings
from app.core.security import PERMISSIONS, Principal, Role
from app.main import create_app
from app.services import integrity, reports
from tests.conftest import add_identity, make_token

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
MIGRATION = ROOT / "supabase" / "migrations" / "0004_ops_audit_resilience.sql"
SIGNED_FIELDS = ("actor_id", "actor_role", "session_id", "aal", "source_ip", "action", "entity_type", "entity_id",
                 "outcome", "error_code", "request_id", "details", "signed_at", "key_id")


# --------------------------------------------------------------------------- shared fakes
class FakeConn:
    """Minimal async connection double. Statements containing `fail_on` raise like a dead DB."""

    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on
        self.executed: list[tuple[str, tuple | dict | None]] = []

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self.fail_on and self.fail_on in sql:
            raise psycopg.OperationalError("connection to server failed: relation \"events\"")

    @asynccontextmanager
    async def transaction(self):
        yield self

    def inserts(self, table: str = "public.events") -> list[tuple]:
        return [p for s, p in self.executed if s.startswith(f"insert into {table}")]


def fake_transaction(conn: FakeConn):
    @asynccontextmanager
    async def _tx(principal):
        yield conn
    return _tx


def principal(role: Role = Role.NURSE) -> Principal:
    now = int(time.time())
    return Principal(user_id=uuid.uuid4(), email=f"{role.value}@example.test", role=role, session_id=str(uuid.uuid4()),
                     aal="aal2" if role is Role.ADMIN else "aal1", issued_at=now, auth_time=now, permissions=PERMISSIONS[role])


def row_from_params(params: tuple) -> dict:
    keys = ("actor_id", "actor_role", "action", "entity_type", "entity_id", "outcome", "request_id", "details",
            "source_ip", "session_id", "aal", "error_code", "signed_at", "key_id", "signature")
    row = dict(zip(keys, params, strict=True))
    row["details"] = json.loads(row["details"])
    return row


@pytest.fixture
def alerts(monkeypatch):
    raised: list[str] = []

    async def fake_notify(kind, details=None):
        raised.append(kind)

    monkeypatch.setattr(audit, "notify_admins", fake_notify)
    audit._buffer.clear()
    yield raised
    audit._buffer.clear()


@pytest.fixture
def sec_capture():
    records: list[logging.LogRecord] = []

    class H(logging.Handler):
        def emit(self, record):
            records.append(record)

    h = H(level=logging.DEBUG)
    logging.getLogger("acme.security").addHandler(h)
    yield records
    logging.getLogger("acme.security").removeHandler(h)


def run(coro):
    return asyncio.run(coro)


_REAL_RECORD = audit.record_event  # the `identities` fixture replaces audit.record_event with a recorder


@pytest.fixture(autouse=True)
def _reset_degraded_state():
    from app.services import resilience

    resilience.state.db_failures.clear()
    resilience.state.forced_level = None
    yield
    resilience.state.db_failures.clear()
    resilience.state.forced_level = None


# --------------------------------------------------------------------------- T46 / T229 confidentiality
SECRET_PATTERNS = [re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
                   re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), re.compile(r"Sup3r-Secret"), re.compile(r"chest pain")]


def test_t46_redact_masks_tokens_emails_passwords_and_clinical_text():
    jwt = make_token()
    out = app_logging.redact({"msg": f"Bearer {jwt} by nurse@acme.test password=Sup3r-Secret",
                              "note": "chest pain", "body": {"x": 1}, "has_note": True, "password_min_length": 12,
                              "nested": [{"email": "a@b.co"}]})
    text = json.dumps(out)
    for p in SECRET_PATTERNS:
        assert not p.search(text), p.pattern
    assert out["has_note"] is True and out["password_min_length"] == 12  # non-content values kept


def test_t46_redacting_filter_rewrites_record_and_caps_length():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "token=%s %s", (make_token(), "y" * 5000), None)
    assert app_logging.RedactingFilter().filter(rec)
    assert "eyJ" not in rec.msg and len(rec.msg) <= app_logging.MAX_ENTRY_CHARS and rec.args == ()


def test_t229_formatted_logs_and_audit_rows_have_no_confidential_data(monkeypatch, alerts):
    formatter = app_logging.JsonFormatter()
    lines: list[str] = []

    class H(logging.Handler):
        def emit(self, record):
            lines.append(formatter.format(record))

    root = logging.getLogger()
    h = H()
    root.addHandler(h)
    try:
        logging.getLogger("acme.test").info("login attempt", extra={"email": "nurse@acme.test", "authorization": f"Bearer {make_token()}",
                                                                    "password": "Sup3r-Secret"})
        conn = FakeConn()
        run(audit.record_event(principal(), "observation.created", "patient", str(uuid.uuid4()),
                               details={"body": "chest pain", "email": "x@acme.test"}, conn=conn))
    finally:
        root.removeHandler(h)
    persisted = json.dumps([row_from_params(p) for p in conn.inserts()])
    for text in ["\n".join(lines), persisted]:
        for p in SECRET_PATTERNS:
            assert not p.search(text), p.pattern


def test_t229_production_log_level_is_info():
    app_logging.configure_logging(production=True)
    try:
        assert logging.getLogger().level == logging.INFO
        assert any(isinstance(f, app_logging.RedactingFilter) for f in logging.getLogger().handlers[0].filters)
    finally:
        app_logging.configure_logging(production=False)


def test_t46_no_raw_body_or_header_logging_in_code():
    offenders = []
    for path in (BACKEND / "app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        if re.search(r"log\w*\.\w+\(.*(request\.headers|await request\.(body|json)\(\))", src) or re.search(r"^\s*print\(", src, re.M):
            offenders.append(path.name)
    assert offenders == [] or offenders == ["cli.py"], offenders  # CLI prints one-time credentials to the operator only


# --------------------------------------------------------------------------- T45 / T315 security events
def _events(records) -> list[str]:
    return [r.getMessage() for r in records]


def test_t315_detection_points_are_logged_with_utc_ms_context(client, identities, sec_capture):
    nurse = add_identity(identities, "nurse")
    h = {"Authorization": f"Bearer {make_token(nurse)}", "x-vercel-forwarded-for": "203.0.113.7"}
    client.get("/v1/wards", headers={"Authorization": "Bearer not-a-jwt"})                     # AE: invalid token
    client.delete("/v1/alarms", headers=h)                                                   # RE2: unsupported method
    client.post("/v1/simulation/reset", headers=h, json={"confirm_text": "RESET DEMO DATA", "acknowledged": True})  # ACE3
    client.post(f"/v1/alarms/{uuid.uuid4()}/acknowledge", headers=h, json={"acknowledged": True, "role": "admin"})  # AE10
    client.get("/v1/does-not-exist", headers=h)                                               # forced browsing
    names = _events(sec_capture)
    for expected in ("authn_failed", "method_not_allowed", "input_validation_failed", "resource_not_found"):
        assert expected in names, names
    assert ("authz.denied", "route", "/v1/simulation/reset", "denied") in identities["__events__"]
    with_ctx = [r for r in sec_capture if r.getMessage() == "method_not_allowed"][0]
    assert with_ctx.ip == "203.0.113.7" and with_ctx.path == "/v1/alarms" and with_ctx.outcome == "failure"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00", with_ctx.event_ts)


def test_t45_security_events_use_separate_logger_and_cap_fields(sec_capture):
    app_logging.sec_event("upload_rejected", outcome="failure", reason="x" * 500)
    rec = sec_capture[-1]
    assert rec.name == "acme.security" and len(rec.reason) == app_logging.MAX_FIELD_CHARS


def test_t45_client_ip_ignores_spoofable_x_forwarded_for():
    assert app_logging.client_ip({b"x-forwarded-for": b"6.6.6.6"}, "10.0.0.1") == "10.0.0.1"
    assert app_logging.client_ip({b"x-vercel-forwarded-for": b"203.0.113.9, 10.0.0.1"}, "10.0.0.1") == "203.0.113.9"
    assert app_logging.client_ip({b"x-real-ip": b"not an ip"}, None) is None


# --------------------------------------------------------------------------- T71 / T232 transaction completeness
TRANSACTIONS = ["alarm.acknowledged", "observation.created", "threshold.changed", "monitor.bound", "monitor.unbound",
                "maintenance.recorded", "staff.updated", "simulation.scenario_set", "simulation.advanced", "simulation.reset",
                "report.generated", "file.uploaded"]


@pytest.mark.parametrize("action", TRANSACTIONS)
def test_t232_every_transaction_record_has_who_where_what_when_outcome(action, alerts):
    p = principal(Role.PHYSICIAN)
    conn = FakeConn()
    ctx = app_logging.RequestContext(request_id="req-12345678", source_ip="203.0.113.7", method="POST", path="/v1/x")
    token = app_logging._ctx.set(ctx)
    try:
        run(audit.record_event(p, action, "patient", str(uuid.uuid4()), details={"k": 1}, conn=conn))
    finally:
        app_logging._ctx.reset(token)
    row = row_from_params(conn.inserts()[-1])
    for field in ("actor_id", "actor_role", "session_id", "aal", "source_ip", "action", "entity_type", "entity_id",
                  "outcome", "request_id", "signed_at", "key_id", "signature"):
        assert row[field], field
    assert row["actor_id"] == str(p.user_id) and row["source_ip"] == "203.0.113.7"
    assert datetime.fromisoformat(row["signed_at"]).tzinfo is not None and "." in row["signed_at"]


def test_t232_failures_are_audited_with_error_code(alerts):
    conn = FakeConn()
    run(audit.record_event(principal(), "alarm.ack_rejected", "alarm", "a1", outcome="failure",
                           error_code="already_acknowledged", conn=conn))
    row = row_from_params(conn.inserts()[-1])
    assert row["outcome"] == "failure" and row["error_code"] == "already_acknowledged"


def test_t71_oversized_details_are_truncated(alerts):
    conn = FakeConn()
    run(audit.record_event(principal(), "report.generated", "report", "x",
                           details={f"k{i}": "v" * 300 for i in range(40)}, conn=conn))
    row = row_from_params(conn.inserts()[-1])
    assert len(json.dumps(row["details"])) <= audit.MAX_DETAILS_BYTES


def test_t71_migration_adds_audit_columns():
    sql = MIGRATION.read_text(encoding="utf-8")
    for col in ("source_ip", "session_id", "aal", "error_code", "signed_at", "key_id", "signature"):
        assert f"add column if not exists {col}" in sql


# --------------------------------------------------------------------------- T485 / T486 signatures
def _signed_row(alerts_fixture=None) -> dict:
    conn = FakeConn()
    run(_REAL_RECORD(principal(), "alarm.acknowledged", "alarm", str(uuid.uuid4()),
                     details={"state_after": "active"}, conn=conn))
    return row_from_params(conn.inserts()[-1])


def test_t485_records_are_signed_with_ecdsa_p521_sha512_and_verify(alerts):
    row = _signed_row()
    assert integrity.SIGNATURE_ALGORITHM == "ECDSA-P521-SHA512"
    assert integrity._signing_key().curve.name == "secp521r1"
    assert row["key_id"] == integrity.key_id() and audit.verify_row(row)
    assert "BEGIN PUBLIC KEY" in integrity.public_key_pem()


@pytest.mark.parametrize("field", SIGNED_FIELDS)
def test_t486_tampering_any_signed_field_is_detected(field, alerts):
    row = _signed_row()
    row[field] = {"forged": True} if field == "details" else "00000000-0000-4000-8000-000000000000"
    assert not audit.verify_row(row)


def test_t486_missing_signature_is_not_valid(alerts):
    row = _signed_row()
    row["signature"] = None
    assert not audit.verify_row(row)


def test_t485_chain_covers_signature_columns():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "coalesce('|sig=' || e.signature, '')" in sql and "pg_advisory_xact_lock(hashtext('public.events'))" in sql


def test_t486_integrity_endpoint_reports_invalid_signatures(client, identities, monkeypatch, alerts):
    good, bad = _signed_row(), _signed_row()
    bad["actor_id"] = str(uuid.uuid4())
    good["id"], bad["id"] = 1, 2
    from app.routers import events

    async def fake_one(conn, sql, params=()):
        return {"broken_at": None}

    async def fake_all(conn, sql, params=()):
        return [bad, good]

    async def fake_record(*a, **k):
        return None

    monkeypatch.setattr(events, "transaction", fake_transaction(FakeConn()))
    monkeypatch.setattr(events, "fetch_one", fake_one)
    monkeypatch.setattr(events, "fetch_all", fake_all)
    monkeypatch.setattr(events, "record_event", fake_record)
    admin = add_identity(identities, "admin")
    r = client.get("/v1/events/integrity", headers={"Authorization": f"Bearer {make_token(admin, aal='aal2')}"})
    assert r.status_code == 200
    body = r.json()
    assert body["intact"] is False and body["chain_intact"] is True and body["invalid_signature_ids"] == [2]


# --------------------------------------------------------------------------- T431 / T432 failure handling
def _check_audit_insert_failed(alerts):
    run(audit.record_event(principal(), "simulation.advanced", "simulation", "1", conn=FakeConn(fail_on="public.events")))
    assert alerts == ["audit_insert_failed"] and len(audit._buffer) == 1


def _check_audit_buffer_full(alerts):
    for _ in range(audit.BUFFER_MAX + 1):
        run(audit.record_event(principal(), "report.generated", "report", "x", conn=FakeConn(fail_on="public.events")))
    assert alerts[-1] == "audit_buffer_full" and len(audit._buffer) == audit.BUFFER_MAX


def _check_critical_audit_failed(alerts):
    with pytest.raises(audit.AuditUnavailable):
        run(audit.record_event(principal(), "alarm.acknowledged", "alarm", "a", conn=FakeConn(fail_on="public.events")))
    assert alerts == ["critical_audit_failed"] and not audit._buffer


def _check_audit_signing_failed(alerts, monkeypatch):
    def boom(_):
        raise RuntimeError("hsm down")

    monkeypatch.setattr(integrity, "sign", boom)
    with pytest.raises(audit.AuditUnavailable):
        run(audit.record_event(principal(), "threshold.changed", "ward", "w", conn=FakeConn()))
    run(audit.record_event(principal(), "simulation.advanced", "simulation", "1", conn=FakeConn()))  # minor: no raise
    assert alerts.count("audit_signing_failed") == 2


def _check_log_sink_error(alerts):
    before = app_logging.failure_counters["log_sink_error"]
    handler = app_logging.SafeStreamHandler(stream=None)
    handler.stream = None  # writing raises inside emit -> handleError
    handler.emit(logging.LogRecord("x", logging.INFO, __file__, 1, "m", (), None))
    assert app_logging.failure_counters["log_sink_error"] == before + 1


def _check_alert_store_failed(alerts, monkeypatch):
    real_notify = alerts.real  # type: ignore[attr-defined]

    @asynccontextmanager
    async def dead_tx(principal):
        raise psycopg.OperationalError("down")
        yield  # pragma: no cover

    monkeypatch.setattr("app.db.transaction", dead_tx)
    audit._last_alert.clear()
    before = app_logging.failure_counters["alert_store_failed"]
    run(real_notify("audit_insert_failed", {}))  # must not raise
    assert app_logging.failure_counters["alert_store_failed"] == before + 1


FAILURE_TESTS = {
    "audit_insert_failed": _check_audit_insert_failed,
    "audit_buffer_full": _check_audit_buffer_full,
    "critical_audit_failed": _check_critical_audit_failed,
    "audit_signing_failed": _check_audit_signing_failed,
    "log_sink_error": _check_log_sink_error,
    "alert_store_failed": _check_alert_store_failed,
}


def test_t432_every_catalogued_failure_has_a_test():
    assert set(FAILURE_TESTS) == set(app_logging.FAILURE_POLICY)


@pytest.mark.parametrize("failure", sorted(app_logging.FAILURE_POLICY))
def test_t432_designed_response_for_each_failure(failure, monkeypatch):
    class Alerts(list):
        real = staticmethod(audit.notify_admins)

    alerts = Alerts()

    async def fake_notify(kind, details=None):
        alerts.append(kind)

    monkeypatch.setattr(audit, "notify_admins", fake_notify)
    audit._buffer.clear()
    try:
        fn = FAILURE_TESTS[failure]
        if "monkeypatch" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
            fn(alerts, monkeypatch)
        else:
            fn(alerts)
    finally:
        audit._buffer.clear()


def test_t432_buffer_is_flushed_on_next_successful_write(monkeypatch, alerts):
    run(audit.record_event(principal(), "simulation.advanced", "simulation", "1", conn=FakeConn(fail_on="public.events")))
    good = FakeConn()
    monkeypatch.setattr("app.db.transaction", fake_transaction(good))
    run(audit.record_event(principal(), "auth.logout", "session", "s"))
    assert not audit._buffer and len(good.inserts()) == 2


def _admin_headers(identities) -> dict:
    return {"Authorization": f"Bearer {make_token(add_identity(identities, 'admin'), aal='aal2')}"}


def test_t432_alarm_generation_continues_when_audit_insert_fails(client, identities, monkeypatch, alerts):
    from app.routers import simulation as sim_router

    conn = FakeConn(fail_on="public.events")

    async def fake_advance(c, user_id, steps, expected_version):
        return {"tick": 1, "version": 1, "readings": 10, "raised": 2, "resolved": 0, "evaluation_errors": 0}

    async def fake_watchdog(c, timeout_seconds=30):
        return []

    monkeypatch.setattr(sim_router, "transaction", fake_transaction(conn))
    monkeypatch.setattr(sim_router, "fetch_one", AsyncMock(return_value={"retry_after": 0}))  # shared limit (T1362)
    monkeypatch.setattr(sim_router.simulation, "advance", fake_advance)
    monkeypatch.setattr(sim_router.alarms, "watchdog_sweep", fake_watchdog)
    r = client.post("/v1/simulation/advance", json={"steps": 1, "expected_version": 0}, headers=_admin_headers(identities))
    assert r.status_code == 200 and r.json()["raised"] == 2
    assert alerts == ["audit_insert_failed"]


def test_t432_ack_refused_with_503_when_audit_cannot_be_written(client, identities, monkeypatch, alerts):
    from app.routers import alarms as alarm_router

    conn = FakeConn(fail_on="public.events")
    calls = []

    async def fake_one(c, sql, params=()):
        return {"id": params[0], "state": "active", "acknowledged_at": None}

    async def fake_ack(c, alarm_id, user_id, note):
        calls.append(alarm_id)
        return {"id": alarm_id, "state": "active"}

    monkeypatch.setattr(alarm_router, "transaction", fake_transaction(conn))
    monkeypatch.setattr(alarm_router, "fetch_one", fake_one)
    monkeypatch.setattr(alarm_router.alarm_service, "acknowledge", fake_ack)
    nurse = add_identity(identities, "nurse")
    r = client.post(f"/v1/alarms/{uuid.uuid4()}/acknowledge", json={"acknowledged": True},
                    headers={"Authorization": f"Bearer {make_token(nurse)}"})
    assert r.status_code == 503 and r.json()["code"] == "audit_unavailable"
    assert "relation" not in r.text and "psycopg" not in r.text
    assert alerts == ["critical_audit_failed"] and calls  # the transaction (with the ack) is rolled back by the context


# --------------------------------------------------------------------------- T350 audit protection
def test_t350_events_append_only_and_reset_preserves_audit():
    base = (ROOT / "supabase" / "migrations" / "0001_schema.sql").read_text(encoding="utf-8")
    assert "events are append-only" in base and "before update or delete on public.events" in base
    assert "before truncate on public.events" in base
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "revoke update, delete, truncate on public.events" in sql
    from app.services import simulation

    assert not any("events" in s or "system_alerts" in s for s in simulation.RESET_SQL)
    from app.routers import events

    assert {m for r in events.router.routes for m in r.methods} <= {"GET", "POST"}
    assert not any(r.path == "/v1/events/{event_id}" for r in events.router.routes)


def test_t350_nurse_cannot_verify_or_read_all_events(client, identities):
    nurse = add_identity(identities, "nurse")
    h = {"Authorization": f"Bearer {make_token(nurse)}"}
    assert client.get("/v1/events/integrity", headers=h).status_code == 403
    assert client.get("/v1/events/alerts", headers=h).status_code == 403


# --------------------------------------------------------------------------- T437 / T438 reports
def _rows():
    t = datetime.now(UTC)
    rows = [{"id": i, "occurred_at": t, "actor_id": "u1" if i % 2 else "u2", "actor_role": "nurse",
             "action": "alarm.acknowledged" if i < 4 else "authz.denied", "entity_type": "alarm", "entity_id": f"a{i}",
             "outcome": "success" if i < 4 else "denied", "error_code": None, "source_ip": "203.0.113.7",
             "request_id": "r"} for i in range(1, 14)]
    rows.append({**rows[0], "id": 14, "entity_id": "=cmd|' /C calc'!A0", "action": "alarm.acknowledged"})
    return rows


def test_t437_summary_reduces_by_action_actor_outcome_with_anomalies():
    rows = _rows()
    snapshot = json.dumps(rows, default=str)
    s = reports.summarize_audit(rows, datetime.now(UTC) - timedelta(hours=1), datetime.now(UTC), None)
    assert s["totals_by_action"] == {"alarm.acknowledged": 4, "authz.denied": 10}
    assert s["totals_by_outcome"]["denied"] == 10 and s["suspicious_actors"] == ["u1", "u2"]
    assert s["first_id"] == 1 and s["last_id"] == 14 and s["chain_intact"] is True
    assert json.dumps(rows, default=str) == snapshot  # source rows unchanged and order preserved


def test_t438_audit_query_is_read_only_and_ordered(monkeypatch):
    seen = []

    async def fake_all(conn, sql, params=()):
        seen.append((sql, params))
        return []

    monkeypatch.setattr(reports, "fetch_all", fake_all)
    run(reports.audit_rows(None, datetime.now(UTC) - timedelta(hours=1), datetime.now(UTC), ["alarm.acknowledged"]))
    sql = seen[0][0].strip().lower()
    assert sql.startswith("select") and "order by id" in sql
    assert not re.search(r"\b(update|delete|insert|truncate)\b", sql)


def test_t438_audit_report_forbidden_for_nurse_and_physician(client, identities):
    for role in ("nurse", "physician"):
        uid = add_identity(identities, role)
        assert client.get("/v1/reports/audit", headers={"Authorization": f"Bearer {make_token(uid)}"}).status_code == 403


def test_t438_audit_report_endpoint_is_on_demand_and_audited(client, identities, monkeypatch):
    from app.routers import reports as rep_router

    audited = []

    async def fake_summary(conn, start, end, actions, actor_id, outcome):
        return reports.summarize_audit([r for r in _rows() if not actions or r["action"] in actions], start, end, None)

    async def fake_record(principal, action, *a, **k):
        audited.append(action)

    monkeypatch.setattr(rep_router, "transaction", fake_transaction(FakeConn()))
    monkeypatch.setattr(rep_router, "fetch_one", AsyncMock(return_value={"retry_after": 0}))  # shared limit (T1362)
    monkeypatch.setattr(rep_router.reports, "audit_summary", fake_summary)
    monkeypatch.setattr(rep_router, "record_event", fake_record)
    r = client.get("/v1/reports/audit", params={"actions": "alarm.acknowledged"}, headers=_admin_headers(identities))
    assert r.status_code == 200, r.text
    assert set(r.json()["totals_by_action"]) == {"alarm.acknowledged"} and audited == ["report.generated"]
    assert client.get("/v1/reports/audit", params={"actions": "x'; drop"}, headers=_admin_headers(identities)).status_code == 422


def test_t437_csv_export_neutralises_formula_injection(tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "TMP_ROOT", tmp_path / "acme-reports")
    path, cleanup = reports.build_csv_export(("entity_id",), [{"entity_id": "=cmd|' /C calc'!A0"}, {"entity_id": "<script>x</script>"}])
    try:
        content = Path(path).read_text(encoding="utf-8")
    finally:
        cleanup()
    assert "'=cmd" in content and "<script>x</script>" in content  # inert text, never executed


# --------------------------------------------------------------------------- T159 / T403 errors
LEAK = re.compile(r"(?i)traceback|File \"|/var/task|psycopg|postgrest|syntax error|SELECT |relation \"|supabase")


@pytest.fixture
def boom_client(identities):
    app = create_app()

    async def boom():
        raise RuntimeError('relation "patients" does not exist')

    async def db_down():
        raise psycopg.OperationalError("could not connect to server: supabase.co")

    app.add_api_route("/v1/__test_boom", boom)
    app.add_api_route("/v1/__test_db_down", db_down)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.mark.parametrize("method,path,kw", [
    ("get", "/v1/__test_boom", {}),
    ("get", "/v1/patients/not-a-uuid", {}),
    ("post", f"/v1/alarms/{uuid.uuid4()}/acknowledge", {"content": b"{bad json", "headers": {"Content-Type": "application/json"}}),
    ("get", "/v1/does-not-exist", {}),
    ("patch", "/v1/alarms", {}),
    ("get", "/v1/__test_db_down", {}),
])
def test_t403_errors_are_generic_and_catalogued(boom_client, identities, method, path, kw):
    uid = add_identity(identities, "nurse")
    headers = {"Authorization": f"Bearer {make_token(uid)}", **kw.pop("headers", {})}
    r = boom_client.request(method, path, headers=headers, **kw)
    assert r.status_code >= 400 and not LEAK.search(r.text), r.text
    body = r.json()
    assert set(body) <= {"error", "code", "request_id", "fields", "degraded"}, body
    assert isinstance(body["error"], str) and "error" in body


def test_t159_unhandled_exception_returns_500_generic(boom_client, identities):
    r = boom_client.get("/v1/__test_boom")
    assert r.status_code == 500 and r.json()["code"] == "internal" and r.json()["request_id"]


def test_t159_db_outage_fails_to_known_503_state(boom_client):
    r = boom_client.get("/v1/__test_db_down")
    assert r.status_code == 503 and r.json()["code"] == "monitoring_unavailable" and r.headers["retry-after"]


def test_t403_unknown_user_and_bad_token_get_identical_responses(client, identities):
    a = client.get("/v1/wards", headers={"Authorization": f"Bearer {make_token()}"})
    b = client.get("/v1/wards", headers={"Authorization": "Bearer garbage.token.value"})
    assert a.status_code == b.status_code == 401
    assert {k: v for k, v in a.json().items() if k != "request_id"} == {k: v for k, v in b.json().items() if k != "request_id"}


# --------------------------------------------------------------------------- T105 debug surface
def test_t105_production_has_no_debug_surface(monkeypatch):
    import app.main as main

    prod = Settings(app_env="production")
    monkeypatch.setattr(main, "get_settings", lambda: prod)
    app = main.create_app()
    assert app.debug is False
    with TestClient(app) as c:
        for path in ("/docs", "/redoc", "/openapi.json", "/debug", "/v1/__test_boom"):
            assert c.get(path).status_code == 404, path
        r = c.get("/v1/health")
        assert not {"server", "x-debug", "x-powered-by"} & {h.lower() for h in r.headers}
        assert c.post("/v1/simulation/reset", json={}).status_code in (401, 422)


def test_t105_no_debugger_calls_or_reload_in_deploy():
    for path in (BACKEND / "app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(breakpoint\(\)|pdb\.set_trace|import pdb)", src), path
    assert "--reload" not in (BACKEND / "vercel.json").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- T2599 DSN never logged
def test_t2599_connection_strings_in_log_lines_are_redacted():
    for dsn in ("postgresql://acme_api:Sup3r!Secret#x@localhost:5432/postgres?sslmode=verify-full",
                "postgres://acme_api:p%40ss-W0rd@db.example.supabase.co/postgres"):
        out = app_logging.redact(f"pool error connecting with {dsn}")
        assert "Sup3r" not in out and "p%40ss" not in out, out
        assert "[REDACTED]@" in out
