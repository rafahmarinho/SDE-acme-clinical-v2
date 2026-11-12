"""Clinical safety & resilience tests (skills/clinical-safety-resilience): degraded mode, known
failure states, priority scheme, critical-action warnings, races, deadlocks, watchdog."""

from __future__ import annotations

import asyncio
import random
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import psycopg
import pytest
from fastapi.routing import APIRoute
from psycopg import errors as pg_errors

from app.main import create_app
from app.services import alarms, resilience, simulation
from app.services.resilience import OpClass
from tests.conftest import add_identity, make_token
from tests.test_logging_audit import FakeConn, fake_transaction

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "0004_ops_audit_resilience.sql"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clean_state():
    resilience.state.db_failures.clear()
    resilience.state.forced_level = None
    yield
    resilience.state.db_failures.clear()
    resilience.state.forced_level = None


def _h(identities, role, aal="aal1"):
    # A fresh interactive sign-in (auth_time = now), so step-up protected routes accept the token.
    token = make_token(add_identity(identities, role), aal=aal, auth_time=int(time.time()))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def alarm_env(monkeypatch):
    """Alarms router on a fake DB returning one active alarm."""
    from app.routers import alarms as alarm_router

    conn = FakeConn()
    acks: list[str] = []
    audited: list[str] = []
    row = {"id": uuid.uuid4(), "patient_id": None, "patient_pseudonym": None, "monitor_serial": "MON-0001",
           "type": "low_spo2", "priority": "high", "state": "active", "message": "SpO2 85 below limit 92",
           "raised_at": datetime.now(UTC), "last_seen_at": datetime.now(UTC), "resolved_at": None,
           "acknowledged_at": None, "acknowledged_by_name": None}

    async def fake_one(c, sql, params=()):
        if "for update" in sql:
            return {"id": row["id"], "state": "active", "acknowledged_at": row["acknowledged_at"]}
        return row

    async def fake_all(c, sql, params=()):
        return [row]

    async def fake_ack(c, alarm_id, user_id, note):
        if row["acknowledged_at"] is not None:
            return None
        row["acknowledged_at"] = datetime.now(UTC)
        acks.append(user_id)
        return {"id": alarm_id, "state": "active"}

    async def fake_record(principal, action, *a, **k):
        audited.append(action)

    async def fake_watchdog(c, timeout_seconds=30):
        return []

    monkeypatch.setattr(alarm_router, "transaction", fake_transaction(conn))
    monkeypatch.setattr(alarm_router, "fetch_one", fake_one)
    monkeypatch.setattr(alarm_router, "fetch_all", fake_all)
    monkeypatch.setattr(alarm_router.alarm_service, "acknowledge", fake_ack)
    monkeypatch.setattr(alarm_router.alarm_service, "watchdog_sweep", fake_watchdog)
    monkeypatch.setattr(alarm_router, "record_event", fake_record)
    return {"row": row, "acks": acks, "audited": audited}


# --------------------------------------------------------------------------- T363 / T2280 priority scheme
def _api_routes():
    return [r for r in create_app().routes if isinstance(r, APIRoute)]


def test_t2280_every_route_is_classified():
    untagged = [f"{m} {r.path}" for r in _api_routes() for m in r.methods if resilience.classify(m, r.path) is None]
    assert untagged == []


@pytest.mark.parametrize("method,path,cls", [
    ("POST", "/v1/alarms/123/acknowledge", OpClass.EMERGENCY_SAFETY),
    ("GET", "/v1/alarms", OpClass.EMERGENCY_SAFETY),
    ("POST", "/v1/break-glass", OpClass.EMERGENCY_SAFETY),
    ("GET", "/v1/patients/1/readings", OpClass.MONITORING),
    ("POST", "/v1/simulation/advance", OpClass.MONITORING),
    ("POST", "/v1/patients/1/observations", OpClass.MAIN_FUNCTION),
    ("PUT", "/v1/thresholds/wards/1", OpClass.MAIN_FUNCTION),
    ("POST", "/v1/monitors/1/assignment", OpClass.MAIN_FUNCTION),
    ("GET", "/v1/reports/ward-activity", OpClass.SUPERVISORY),
    ("POST", "/v1/simulation/reset", OpClass.SUPERVISORY),
    ("GET", "/v1/staff", OpClass.SUPERVISORY),
])
def test_t2280_expected_classes(method, path, cls):
    assert resilience.classify(method, path) is cls


def test_t2280_shedding_order(client, identities):
    resilience.state.forced_level = OpClass.MAIN_FUNCTION
    phys = _h(identities, "physician")
    r = client.get("/v1/reports/ward-activity", headers=phys)
    assert r.status_code == 503 and r.json()["code"] == "degraded_mode" and r.headers["retry-after"]
    r = client.post(f"/v1/patients/{uuid.uuid4()}/observations", headers=phys, json={"body": "x"})
    assert r.status_code == 503
    assert client.get("/v1/alarms/system-status", headers=phys).status_code == 200  # emergency never shed


@pytest.mark.parametrize("scenario,expected", [
    ("low_saturation", {"low_spo2": "high"}),
    ("sensor_fault", {"sensor_fault": "medium"}),
    ("connection_loss", {"connection_lost": "high"}),
])
def test_t2280_alarm_priority_for_each_scenario(scenario, expected):
    reading, battery = simulation.generate(scenario, random.Random(1), 100)
    _, conds = alarms.evaluate_monitor(reading, battery, {}, connected=reading is not None, has_patient=True)
    got = {c.type: c.priority for c in conds}
    for t, p in expected.items():
        assert got.get(t) == p, got


def test_t363_low_battery_priority_and_technical_alarms_never_low():
    assert [c.priority for c in alarms.evaluate_device(15, "good", True)] == ["low"]
    assert [c.priority for c in alarms.evaluate_device(8, "good", True)] == ["medium"]
    for t in ("connection_lost", "sensor_fault", "evaluation_error"):
        assert alarms.ALARM_PRIORITY[t] != "low"


def test_t363_supervisory_concurrency_is_bounded():
    assert resilience.CONCURRENCY_LIMITS[OpClass.SUPERVISORY] <= 5
    assert OpClass.EMERGENCY_SAFETY not in resilience.CONCURRENCY_LIMITS


# --------------------------------------------------------------------------- T433 / T434 degraded mode
def test_t434_db_failures_enter_degraded_mode_and_shed_non_essential(client, identities, alarm_env):
    for _ in range(5):
        resilience.note_db_failure()
    nurse, admin = _h(identities, "nurse"), _h(identities, "admin", "aal2")
    status = client.get("/v1/alarms/system-status", headers=nurse).json()
    assert status["mode"] == "degraded" and "supervisory" in status["shed_classes"]
    assert client.get("/v1/alarms", headers=nurse).status_code == 200                 # alarms keep working
    r = client.post(f"/v1/alarms/{alarm_env['row']['id']}/acknowledge", headers=nurse, json={"acknowledged": True})
    assert r.status_code == 200                                                          # ack keeps working
    assert client.get("/v1/staff", headers=admin).status_code == 503                    # staff mgmt deferred
    assert client.get("/v1/reports/audit", headers=admin).status_code == 503            # reports deferred


def test_t433_degraded_window_expires():
    resilience.state.db_failures.append(0.0)  # a failure long ago
    assert resilience.mode()["mode"] == "normal"


# --------------------------------------------------------------------------- T347 / T348 known states
CASES = [
    ("normal", alarms.MonitorState.ONLINE, set()),
    ("low_saturation", alarms.MonitorState.ONLINE, {"low_spo2"}),
    ("sensor_fault", alarms.MonitorState.SENSOR_FAULT, {"sensor_fault"}),
    ("connection_loss", alarms.MonitorState.DISCONNECTED, {"connection_lost"}),
]


@pytest.mark.parametrize("scenario,state,codes", CASES)
def test_t348_scenarios_reach_predefined_state(scenario, state, codes):
    reading, battery = simulation.generate(scenario, random.Random(7), 100)
    view, conds = alarms.evaluate_monitor(reading, battery, {}, connected=reading is not None, has_patient=True)
    assert view.state is state
    assert codes <= {c.type for c in conds}
    if state not in (alarms.MonitorState.ONLINE, alarms.MonitorState.LOW_BATTERY):
        assert view.stale and view.heart_rate is None and view.spo2 is None


def test_t348_low_battery_state():
    reading, battery = simulation.generate("low_battery", random.Random(3), 12)
    view, conds = alarms.evaluate_monitor(reading, battery, {}, connected=True, has_patient=True)
    assert view.state is alarms.MonitorState.LOW_BATTERY and "low_battery" in {c.type for c in conds}


def test_t348_implausible_values_are_a_sensor_fault_not_vitals():
    reading = {"heart_rate": 900, "spo2": 97, "resp_rate": 15, "bp_systolic": 120, "bp_diastolic": 80, "quality": "good"}
    view, conds = alarms.evaluate_monitor(reading, 100, {}, connected=True, has_patient=True)
    assert view.state is alarms.MonitorState.SENSOR_FAULT and view.heart_rate is None
    assert {c.type for c in conds} == {"sensor_fault"}


def test_t347_engine_exception_fails_safe_to_high_alarm(monkeypatch):
    def boom(*a, **k):
        return 1 / 0

    monkeypatch.setattr(alarms, "evaluate_vitals", boom)
    reading = {"heart_rate": 80, "spo2": 97, "resp_rate": 15, "bp_systolic": 120, "bp_diastolic": 80, "quality": "good"}
    view, conds = alarms.evaluate_monitor(reading, 100, {}, connected=True, has_patient=True)
    assert view.state is alarms.MonitorState.UNKNOWN and conds == [alarms.EVALUATION_ERROR] and conds[0].priority == "high"


def test_t347_missing_limits_fall_back_to_safe_defaults():
    assert {c.type for c in alarms.evaluate_vitals({"spo2": 80, "quality": "good"}, {})} == {"low_spo2"}


def test_t347_monitor_state_output_marks_stale_heartbeat_disconnected():
    now = datetime.now(UTC)
    fresh = alarms.monitor_state("online", 90, now - timedelta(seconds=5), now, set())
    stale = alarms.monitor_state("online", 90, now - timedelta(seconds=alarms.HEARTBEAT_TIMEOUT_SECONDS + 1), now, set())
    assert fresh == {"state": "online", "stale": False, "heartbeat_age_seconds": 5.0}
    assert stale["state"] == "disconnected" and stale["stale"] is True
    assert alarms.monitor_state("online", 90, None, now, set())["state"] == "disconnected"
    assert alarms.monitor_state("online", 90, now, now, {"evaluation_error"})["state"] == "unknown"


def test_t348_db_down_returns_defined_503(client, identities, monkeypatch):
    from app.routers import alarms as alarm_router

    def dead(principal):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(alarm_router, "transaction", dead)
    r = client.get("/v1/alarms", headers=_h(identities, "nurse"))
    assert r.status_code == 503 and r.json()["code"] == "monitoring_unavailable" and r.json()["degraded"] is True
    assert resilience.state.degraded  # entering degraded mode is automatic


# --------------------------------------------------------------------------- T342 / T343 critical actions
CRITICAL = [
    ("post", "/v1/alarms/{id}/acknowledge", "nurse", {"note": "seen"}),
    ("post", "/v1/simulation/scenario", "admin", {"scenario": "low_saturation"}),
    ("post", "/v1/simulation/reset", "admin", {"confirm_text": "RESET DEMO DATA"}),
    ("post", "/v1/simulation/reset", "admin", {"acknowledged": True}),
]


@pytest.mark.parametrize("method,path,role,body", CRITICAL)
def test_t343_api_requires_explicit_acknowledgement(client, identities, method, path, role, body):
    r = client.request(method, path.format(id=uuid.uuid4()), headers=_h(identities, role, "aal2"), json=body)
    assert r.status_code == 422, r.text


def test_t342_ack_response_repeats_that_condition_is_not_resolved(client, identities, alarm_env):
    nurse = _h(identities, "nurse")
    r = client.post(f"/v1/alarms/{alarm_env['row']['id']}/acknowledge", headers=nurse, json={"acknowledged": True, "note": "seen"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "active" and "does not resolve the condition" in body["notice"] and "recorded" in body["notice"]
    again = client.post(f"/v1/alarms/{alarm_env['row']['id']}/acknowledge", headers=nurse, json={"acknowledged": True})
    assert "already acknowledged" in again.json()["notice"]
    assert alarm_env["audited"] == ["alarm.acknowledged", "alarm.ack_rejected"]


def test_t342_scenario_and_reset_responses_carry_warnings(client, identities, monkeypatch):
    from app.routers import simulation as sim_router

    async def fake_set(*a, **k):
        return None

    async def fake_state(conn):
        return {"scenario": "low_saturation", "tick": 0, "version": 1, "updated_at": datetime.now(UTC)}

    async def fake_record(*a, **k):
        return None

    monkeypatch.setattr(sim_router, "transaction", fake_transaction(FakeConn()))
    monkeypatch.setattr(sim_router, "fetch_one", AsyncMock(return_value={"retry_after": 0}))  # shared limit (T1362)
    monkeypatch.setattr(sim_router.simulation, "set_scenario", fake_set)
    monkeypatch.setattr(sim_router.simulation, "reset", fake_set)
    monkeypatch.setattr(sim_router, "_state", fake_state)
    monkeypatch.setattr(sim_router, "record_event", fake_record)
    admin = _h(identities, "admin", "aal2")
    r = client.post("/v1/simulation/scenario", headers=admin, json={"scenario": "low_saturation", "acknowledged": True})
    assert r.status_code == 200 and "audit log" in r.json()["notice"]
    r = client.post("/v1/simulation/reset", headers=admin, json={"confirm_text": "RESET DEMO DATA", "acknowledged": True})
    assert r.status_code == 200 and "audit trail was preserved" in r.json()["notice"]


# --------------------------------------------------------------------------- T205 races
def test_t205_ack_is_atomic_and_column_scoped():
    sql = alarms.ACK_SQL.lower()
    assert "where id = %s and acknowledged_at is null" in sql
    assert "state" not in sql.split("set", 1)[1].split("where", 1)[0]  # never touches the condition


def test_t205_concurrent_acks_record_exactly_one(client, identities, alarm_env):
    nurse = _h(identities, "nurse")
    url = f"/v1/alarms/{alarm_env['row']['id']}/acknowledge"
    results = [client.post(url, headers=nurse, json={"acknowledged": True}) for _ in range(20)]
    assert all(r.status_code == 200 for r in results)
    assert len(alarm_env["acks"]) == 1 and alarm_env["row"]["state"] == "active"


class SimConn(FakeConn):
    def __init__(self, locked: bool = True, version: int = 0):
        super().__init__()
        self.locked, self.version = locked, version


def _patch_sim_db(monkeypatch, conn: SimConn, state: dict):
    async def fake_one(c, sql, params=()):
        if "pg_try_advisory_xact_lock" in sql:
            return {"locked": c.locked}
        if "from public.simulation_state" in sql:
            return dict(state)
        return None

    async def fake_all(c, sql, params=()):
        return []

    async def fake_exec(c, sql, params=()):
        c.executed.append((sql, params))
        return 1

    monkeypatch.setattr(simulation, "fetch_one", fake_one)
    monkeypatch.setattr(simulation, "fetch_all", fake_all)
    monkeypatch.setattr(simulation, "execute", fake_exec)


def test_t205_second_concurrent_advance_gets_409(monkeypatch):
    state = {"scenario": "normal", "monitor_scenarios": {}, "tick": 0, "version": 0, "integrity_mac": None}
    busy = SimConn(locked=False)
    _patch_sim_db(monkeypatch, busy, state)
    with pytest.raises(simulation.DomainError) as exc:
        run(simulation.advance(busy, str(uuid.uuid4()), 1, 0))
    assert exc.value.status_code == 409


def test_t205_stale_version_rejected_and_lock_taken_first(monkeypatch):
    state = {"scenario": "normal", "monitor_scenarios": {}, "tick": 4, "version": 7, "integrity_mac": None}
    conn = SimConn()
    _patch_sim_db(monkeypatch, conn, state)
    with pytest.raises(simulation.DomainError) as exc:
        run(simulation.advance(conn, str(uuid.uuid4()), 1, 6))
    assert exc.value.status_code == 409
    assert conn.executed[0][0].startswith("set local lock_timeout")


def test_t205_reset_waits_on_the_same_lock_and_preserves_audit(monkeypatch):
    state = {"scenario": "normal", "monitor_scenarios": {}, "tick": 4, "version": 7, "integrity_mac": None}
    conn = SimConn()
    _patch_sim_db(monkeypatch, conn, state)
    run(simulation.reset(conn, str(uuid.uuid4())))
    sqls = [s for s, _ in conn.executed]
    assert "pg_advisory_xact_lock(hashtext(%s))" in sqls[1] and conn.executed[1][1] == (simulation.SIM_LOCK_KEY,)
    assert not any("events" in s for s in sqls)
    assert any("integrity_mac" in s for s in sqls)  # baseline re-sealed


def test_t205_binding_uniqueness_enforced_by_constraints():
    base = (ROOT / "supabase" / "migrations" / "0001_schema.sql").read_text(encoding="utf-8")
    assert "monitor_assignments_active_monitor on public.monitor_assignments(monitor_id) where unassigned_at is null" in base
    assert "monitor_assignments_active_bed on public.monitor_assignments(bed_id) where unassigned_at is null" in base
    assert "alarms_one_active_per_condition" in base


def test_t205_no_module_level_mutable_simulation_state():
    src = (ROOT / "backend" / "app" / "services" / "simulation.py").read_text(encoding="utf-8")
    assert not re.search(r"^(?!_)[a-z_]+\s*(:\s*\w+)?\s*=\s*(\{|\[|dict\(|list\()", src, re.M)


# --------------------------------------------------------------------------- T633 deadlock / recursion
def test_t633_bounded_retry_on_deadlock():
    calls = []

    async def flaky():
        calls.append(1)
        raise pg_errors.DeadlockDetected("deadlock")

    with pytest.raises(pg_errors.DeadlockDetected):
        run(resilience.with_retry(flaky, attempts=3, base_delay=0))
    assert len(calls) == 3

    attempts = []

    async def once():
        attempts.append(1)
        if len(attempts) == 1:
            raise pg_errors.LockNotAvailable("lock timeout")
        return "ok"

    assert run(resilience.with_retry(once, base_delay=0)) == "ok" and len(attempts) == 2


def test_t633_lock_errors_map_to_503_busy(client, identities, monkeypatch):
    from app.routers import alarms as alarm_router

    def locked(principal):
        raise pg_errors.LockNotAvailable("canceling statement due to lock timeout")

    monkeypatch.setattr(alarm_router, "transaction", locked)
    r = client.get("/v1/alarms", headers=_h(identities, "nurse"))
    assert r.status_code == 503 and r.json()["code"] == "busy" and "lock" not in r.text


def test_t633_services_never_call_the_api_over_http_and_triggers_do_not_recurse():
    for name in ("alarms", "simulation", "reports", "resilience", "integrity", "files"):
        path = ROOT / "backend" / "app" / "services" / f"{name}.py"
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(httpx|requests|urllib|aiohttp)", src, re.M), path.name
    sql = MIGRATION.read_text(encoding="utf-8")
    trigger_fn = sql.split("create or replace function public.events_hash_chain()", 1)[1].split("end $$;", 1)[0]
    assert "update public.events" not in trigger_fn and "insert into public.events" not in trigger_fn
    assert "lock_order" in (ROOT / "backend" / "app" / "services" / "simulation.py").read_text(encoding="utf-8").lower()


# --------------------------------------------------------------------------- T4602 watchdog
def test_t4602_watchdog_sql_uses_heartbeat_age_for_any_bound_monitor():
    sql = MIGRATION.read_text(encoding="utf-8")
    fn = sql.split("create or replace function public.watchdog_sweep", 1)[1]
    assert "last_heartbeat_at < now() - make_interval(secs => p_timeout_seconds)" in fn
    assert "'connection_lost', 'high'" in fn and "status = 'offline'" in fn
    assert "scenario" not in fn.split("$$", 2)[1]  # independent of the simulation scenario
    assert "cron.schedule('acme-watchdog'" in sql


def test_t4602_watchdog_runs_on_alarm_reads_and_ticks(monkeypatch):
    seen = []

    async def fake_all(conn, sql, params=()):
        seen.append((sql, params))
        return [{"monitor_id": str(uuid.uuid4()), "alarm_raised": True}]

    monkeypatch.setattr(alarms, "fetch_all", fake_all)
    lost = run(alarms.watchdog_sweep(None))
    assert len(lost) == 1 and "public.watchdog_sweep(%s)" in seen[0][0] and seen[0][1] == (alarms.HEARTBEAT_TIMEOUT_SECONDS,)
    src = (ROOT / "backend" / "app" / "routers" / "alarms.py").read_text(encoding="utf-8")
    assert src.count("await _run_watchdog(conn)") >= 2
    assert "watchdog_sweep" in (ROOT / "backend" / "app" / "routers" / "simulation.py").read_text(encoding="utf-8")


def test_t4602_heartbeat_recovery_returns_monitor_online():
    src = (ROOT / "backend" / "app" / "services" / "simulation.py").read_text(encoding="utf-8")
    assert "when %s and status = 'offline' then 'online'" in src


def test_t4602_watchdog_failure_never_hides_alarms(client, identities, alarm_env, monkeypatch):
    from app.routers import alarms as alarm_router

    async def broken(c, timeout_seconds=30):
        raise psycopg.errors.UndefinedFunction("function public.watchdog_sweep does not exist")

    monkeypatch.setattr(alarm_router.alarm_service, "watchdog_sweep", broken)
    r = client.get("/v1/alarms", headers=_h(identities, "nurse"))
    assert r.status_code == 200 and r.json()["items"][0]["type"] == "low_spo2"
