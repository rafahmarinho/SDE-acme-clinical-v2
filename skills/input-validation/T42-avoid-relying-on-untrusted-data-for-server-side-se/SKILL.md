---
name: t42-avoid-relying-on-untrusted-data-for-server-side-se
description: Stop ACME Clinical from selecting report kinds, simulation scenarios, templates, files or code paths directly from user-supplied strings; map them through strict server-side allowlists (enums) and bound numeric inputs such as simulation steps and report ranges.
---

# T42: Avoid relying on untrusted data for server-side selection

**Category:** CODE_FIX
**SD Elements:** [T42](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T42/)
**Priority:** 10/10 · **Phase:** development

**Spec Context:**
> "Prepare dados de demonstração com doze pacientes e dez monitores. Inclua uma área para"
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: Prepare demo data with twelve patients and ten monitors. Include an area to choose scenarios, advance the simulation, view events and reset the data. The results)
> Source: specs/PRD.md, lines 41-43

**What the spec implies (naive approach):**
"Choose scenarios" and "reports" are easy to implement as `getattr(simulation, f"scenario_{name}")`, `importlib.import_module(name)` or `open(f"templates/{kind}.csv")`, with `steps` taken straight from the request. A crafted name selects unintended functions or files; a huge `steps` value turns "advance the simulation" into a resource-exhaustion DoS.

**Secure Implementation Pattern:**
```python
# backend/app/routers/simulation.py
from enum import StrEnum
from typing import Annotated
from pydantic import Field
from app.schemas import Strict

class Scenario(StrEnum):
    normal = "normal"; low_spo2 = "low_spo2"; low_battery = "low_battery"
    sensor_fault = "sensor_fault"; connection_lost = "connection_lost"

class ScenarioIn(Strict):
    scenario: Scenario                                   # 422 for anything else
    monitor_id: UUID | None = None

class AdvanceIn(Strict):
    steps: Annotated[int, Field(ge=1, le=60)] = 1        # range-bound: loop counter from input

HANDLERS = {Scenario.normal: sim.normal, Scenario.low_spo2: sim.low_spo2,   # explicit map, no getattr
            Scenario.low_battery: sim.low_battery, Scenario.sensor_fault: sim.sensor_fault,
            Scenario.connection_lost: sim.connection_lost}

@router.post("/scenario", response_model=SimulationActionOut)
async def choose(body: ScenarioIn, principal=Depends(require(Perm.simulation_control))):
    return await HANDLERS[body.scenario](principal, body.monitor_id)
```

**Implementation Guidance:**
- Simulation (`backend/app/routers/simulation.py`, `backend/app/services/simulation.py`): scenarios are an `Enum`/`Literal`; dispatch through an explicit dict. Bound `steps` and any per-request tick counts.
- Reports (`backend/app/routers/reports.py`, `backend/app/services/reports.py`): resolve the report kind via `report_kind()`/`ReportKind`; bound date ranges (for example at most 31 days) and row counts (`MAX_AUDIT_ROWS`).
- Never pass request values to `getattr`, `importlib`, `open`, `Path(...)`, template names or Storage paths; files are resolved by ID (T50).
- Frontend routing in `frontend/src/App.tsx` is client-side only; the server never selects views by name.
- Use `Strict` models (`extra="forbid"`) so unexpected selectors are rejected rather than ignored.
- Reference: SD Elements guidance for T42.

**Success Criteria:**
- [ ] `grep -rn "getattr(\|import_module\|__import__" backend/app/routers backend/app/services` has no use with request data.
- [ ] Pytest: `POST /simulation/scenario {"scenario":"__class__"}` -> 422; `POST /simulation/advance {"steps": 100000}` -> 422; report kind `../../etc/passwd` -> 400/422.
- [ ] Report date range above the documented maximum is rejected.

**Status:** Applied
