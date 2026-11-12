---
name: t363-design-a-priority-scheme-for-application-services
description: Define an ACME Clinical priority scheme for operations (emergency/safety alarms, live monitoring, core clinical functions, supervisory/admin and simulation tooling) and a clinical alarm priority scheme, so low-priority work is shed first when resources are scarce.
---

# T363: Design a priority scheme for application services and operations

**Category:** CODE_FIX
**SD Elements:** [T363](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T363/)
**Priority:** 8/10 · **Phase:** architecture-design

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: "frontend. The generation of readings, alarms and reports must be done in Python. The")
> Source: specs/PRD.md, line 21

> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: "ward view, patient list and detail, live monitoring, alarms, devices,")
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
Reading generation, alarm evaluation and report rendering would all run in the same FastAPI process with equal priority. A burst of PDF report requests or a fast-forwarded simulation could delay alarm evaluation, and all alarms would look the same regardless of severity.

**Secure Implementation Pattern:**
```python
# backend/app/core/priority.py
class OpClass(IntEnum):
    EMERGENCY_SAFETY = 0   # alarm evaluation, alarm ack, connection-loss watchdog, break-glass
    MONITORING = 1         # live vitals snapshot/stream, heartbeats, ingest
    MAIN_FUNCTION = 2      # observations, monitor-bed binding, maintenance, thresholds
    SUPERVISORY = 3        # reports, staff mgmt, audit review, simulation scenarios/reset, 3D view

LIMITS = {OpClass.EMERGENCY_SAFETY: None, OpClass.MONITORING: 200,
          OpClass.MAIN_FUNCTION: 50, OpClass.SUPERVISORY: 5}       # concurrent slots per instance
_sems = {c: asyncio.Semaphore(n) for c, n in LIMITS.items() if n}

def op_class(c: OpClass):
    async def dep():
        if load.shed_level() >= c and c != OpClass.EMERGENCY_SAFETY:
            raise HTTPException(503, "Service busy, try again", headers={"Retry-After": "15"})
        sem = _sems.get(c)
        if sem is None: yield; return
        async with sem: yield
    return Depends(dep)

# clinical alarm priority (shown and sorted in UI, drives escalation timers)
class AlarmPriority(IntEnum):
    HIGH = 0     # SpO2 critically low, asystole-like ECG, connection lost, sensor fault on critical pt
    MEDIUM = 1   # SpO2 low, HR out of range, low battery < 10 %
    LOW = 2      # low battery < 20 %, maintenance due
```

**Implementation Guidance:**
- Tag every router operation in `backend/app/routers/*.py` with `op_class(...)`; a test fails if any route lacks one.
- Scarcity scenarios: report bursts, simulation "advance" fast-forwarding many ticks, many Realtime clients, DB pool exhaustion. `load.shed_level()` rises with DB pool wait time / error rate, shedding SUPERVISORY first, then MAIN_FUNCTION.
- Keep alarm evaluation independent of report rendering: render reports asynchronously (queued job) with small concurrency; simulation advance is capped per request.
- Separate DB pools per class (small pool for reports) so supervisory work cannot exhaust connections needed for alarms.
- Alarm priority (IEC 60601-1-8 inspired): HIGH/MEDIUM/LOW with distinct colors, sounds and re-alert intervals in `frontend/src/components/AlarmBanner.tsx`; technical alarms (connection loss, sensor fault) are never LOW.
- Reference: SD Elements guidance for T363.

**Success Criteria:**
- [ ] Every route has an `OpClass`; documented table of classes exists in the README.
- [ ] Under induced load, SUPERVISORY requests return 503 before any EMERGENCY_SAFETY request is delayed.
- [ ] Alarms are sorted and displayed by `AlarmPriority`, with tests for the mapping of each scenario.

**Status:** Applied
