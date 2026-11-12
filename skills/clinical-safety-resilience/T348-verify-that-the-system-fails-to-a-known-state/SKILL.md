---
name: t348-verify-that-the-system-fails-to-a-known-state
description: Test that each ACME Clinical unit (simulated monitor, ingestion, alarm engine, live UI, database connection) fails to its predefined safe state and output under injected faults such as sensor failure, connection loss, low battery and backend errors.
---

# T348: Verify that the system fails to a known state

**Category:** CODE_FIX
**SD Elements:** [T348](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T348/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "acontecendo. Simule leituras normais, saturação baixa, bateria fraca, problema no sensor e"
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...happening. Simulate normal readings, low saturation, low battery, sensor problem and connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, lines 37-39

**What the spec implies (naive approach):**
Scenarios would be demoed manually by clicking through the simulation area, without assertions on the exact resulting state. Regressions (e.g. stale values shown after disconnect) would only be noticed in a demo.

**Secure Implementation Pattern:**
```python
# backend/tests/test_fail_known_state.py
import pytest
from app.services.alarms import evaluate, MonitorState

CASES = [
    ("normal",          dict(spo2=97),                 MonitorState.ONLINE,       set()),
    ("low_saturation",  dict(spo2=84),                 MonitorState.ONLINE,       {"SPO2_LOW"}),
    ("low_battery",     dict(battery_pct=8),           MonitorState.ONLINE,       {"LOW_BATTERY"}),
    ("sensor_fault",    dict(sensor_status="fault"),   MonitorState.SENSOR_FAULT, {"SENSOR_FAULT"}),
    ("connection_loss", None,                          MonitorState.DISCONNECTED, {"CONNECTION_LOST"}),
    ("implausible",     dict(hr=900),                  MonitorState.SENSOR_FAULT, {"SENSOR_FAULT"}),
]

@pytest.mark.parametrize("name,overrides,state,codes", CASES)
def test_scenarios_reach_predefined_state(make_reading, monitor, now, name, overrides, state, codes):
    reading = None if overrides is None else make_reading(**overrides)
    view, alarms = evaluate(reading, monitor, now)
    assert view.state == state
    assert {a.code for a in alarms} >= codes
    if state != MonitorState.ONLINE:
        assert view.hr is None and view.spo2 is None and view.stale

def test_engine_exception_fails_safe(monkeypatch, make_reading, monitor, now):
    monkeypatch.setattr("app.services.alarms.physiological_alarms", lambda *a: 1 / 0)
    view, alarms = evaluate(make_reading(), monitor, now)
    assert view.state == MonitorState.UNKNOWN and alarms[0].code == "EVALUATION_ERROR"

async def test_db_down_returns_defined_error(client_as, break_db):
    r = await client_as("nurse").get("/api/wards/1/live")
    assert r.status_code == 503 and r.json()["code"] == "MONITORING_UNAVAILABLE"
```

**Implementation Guidance:**
- Drive each failure through the simulation API too (`POST /api/simulation/scenarios`), then assert persisted monitor state, alarms and events.
- Frontend (vitest): `VitalTile` renders `--` and "No signal" for stale data; `LiveWard` shows a "Monitoring unavailable" banner on 503 instead of an empty, normal-looking view.
- Fault injection for infrastructure: DB connection failure, Realtime disconnect, timeouts — each must map to a defined error code from `backend/app/core/errors.py`.
- Reference: SD Elements guidance for T348.

**Success Criteria:**
- [ ] All scenario cases pass and match the state table documented for T347.
- [ ] Engine exceptions and DB outages produce predefined outputs (alarm/503 code).
- [ ] Frontend tests confirm no stale numeric vitals are shown.

**Status:** Pending
