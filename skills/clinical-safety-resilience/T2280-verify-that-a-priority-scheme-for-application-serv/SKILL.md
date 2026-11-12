---
name: t2280-verify-that-a-priority-scheme-for-application-serv
description: Verify that every ACME Clinical operation is classified as emergency/safety, monitoring, main function or supervisory, and that under resource scarcity low-priority work is disabled while alarm processing continues.
---

# T2280: Verify that a priority scheme for application services and operations is designed

**Category:** CODE_FIX
**SD Elements:** [T2280](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2280/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: "frontend. The generation of readings, alarms and reports must be done in Python. The")
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
A priority scheme on paper is not enough; new endpoints get added untagged, and shedding logic may never trigger. This verification keeps the T363 design honest.

**Secure Implementation Pattern:**
```python
# backend/tests/test_priority_scheme.py
from fastapi.routing import APIRoute
from app.main import app
from app.core.priority import OpClass

EXPECTED = {
    "/api/alarms/{alarm_id}/ack": OpClass.EMERGENCY_SAFETY,
    "/api/wards/{ward_id}/live": OpClass.MONITORING,
    "/api/observations": OpClass.MAIN_FUNCTION,
    "/api/reports": OpClass.SUPERVISORY,
    "/api/simulation/reset": OpClass.SUPERVISORY,
}

def classes_of(route):
    return [getattr(d.call, "__op_class__", None) for d in route.dependant.dependencies]

def test_every_route_is_classified():
    untagged = [r.path for r in app.routes if isinstance(r, APIRoute)
                and not any(c is not None for c in classes_of(r))]
    assert untagged == []

def test_expected_classes():
    routes = {r.path: r for r in app.routes if isinstance(r, APIRoute)}
    for path, cls in EXPECTED.items():
        assert cls in classes_of(routes[path])

async def test_shedding_order(client_as, force_shed_level, observation_payload):
    force_shed_level(OpClass.MAIN_FUNCTION)
    assert (await client_as("physician").post("/api/reports", json={})).status_code == 503
    assert (await client_as("nurse").post("/api/observations", json=observation_payload)).status_code == 503
    assert (await client_as("nurse").get("/api/alarms?active=true")).status_code == 200
```

**Implementation Guidance:**
- Verify the four categories exist and are documented with examples from ACME Clinical (see T363 table).
- Route-introspection test ensures each route is classified (have `op_class()` set an `__op_class__` attribute on its dependency).
- Simulate scarcity (force shed level, saturate the report pool) and assert the order in which features are disabled.
- Verify alarm priorities: each scenario (low saturation, sensor fault, connection loss, low battery) maps to the expected `AlarmPriority`.
- Reference: SD Elements guidance for T2280.

**Success Criteria:**
- [ ] Classification and shedding-order tests pass in CI.
- [ ] Alarm priority mapping test passes for all simulated scenarios.
- [ ] Design document reviewed and linked from README.

**Status:** Pending
