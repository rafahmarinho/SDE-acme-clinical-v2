---
name: t347-fail-to-a-known-state-with-predefined-outputs
description: Define safe default states and outputs for every ACME Clinical unit (simulated monitor, reading ingestion, alarm engine, live view) so sensor faults, low battery, connection loss or backend errors produce explicit technical alarms and blanked values, never stale or silently normal vitals.
---

# T347: Fail to a known state with predefined outputs

**Category:** CODE_FIX
**SD Elements:** [T347](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T347/)
**Priority:** 4/10 · **Phase:** development

**Spec Context:**
> "acontecendo. Simule leituras normais, saturação baixa, bateria fraca, problema no sensor e"
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...happening. Simulate normal readings, low saturation, low battery, sensor problem and connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, lines 37-39

**What the spec implies (naive approach):**
When a simulated sensor fails or a monitor disconnects, the UI would keep showing the last numbers (looking normal) and the alarm engine, receiving no data, would raise nothing. An exception in alarm evaluation could also be swallowed, leaving alarms silently inactive.

**Secure Implementation Pattern:**
```python
# backend/app/services/alarms.py
class MonitorState(StrEnum):
    ONLINE = "online"; LOW_BATTERY = "low_battery"
    SENSOR_FAULT = "sensor_fault"; DISCONNECTED = "disconnected"; UNKNOWN = "unknown"

class VitalsView(BaseModel):            # predefined output contract for the UI
    hr: int | None; spo2: int | None; rr: int | None; bp: str | None
    state: MonitorState; stale: bool

def evaluate(reading: Reading | None, monitor: Monitor, now: datetime) -> tuple[VitalsView, list[Alarm]]:
    try:
        if reading is None or now - monitor.last_heartbeat_at > HEARTBEAT_TIMEOUT:
            return VitalsView(hr=None, spo2=None, rr=None, bp=None,
                              state=MonitorState.DISCONNECTED, stale=True), \
                   [technical_alarm(monitor, "CONNECTION_LOST", Priority.HIGH)]
        if reading.sensor_status != "ok" or not reading.is_plausible():
            return blank(monitor, MonitorState.SENSOR_FAULT), [technical_alarm(monitor, "SENSOR_FAULT", Priority.HIGH)]
        alarms = physiological_alarms(reading, monitor.thresholds)
        if reading.battery_pct < 15:
            alarms.append(technical_alarm(monitor, "LOW_BATTERY", Priority.MEDIUM))
        return to_view(reading), alarms
    except Exception:
        log.exception("alarm evaluation failed", extra={"monitor_id": str(monitor.id)})
        # Fail-safe: unknown state is surfaced as an alarm, never as "all normal"
        return blank(monitor, MonitorState.UNKNOWN), [technical_alarm(monitor, "EVALUATION_ERROR", Priority.HIGH)]
```

**Implementation Guidance:**
- For each unit, document default output and failure state in `backend/app/services/README` or docstrings: simulator (`services/simulation.py`) emits `sensor_status`; ingestion rejects implausible values (Pydantic ranges) and records a fault; alarm engine (`services/alarms.py`) fails to "technical alarm active"; frontend live tile (`frontend/src/components/VitalTile.tsx`) shows `--` with "No signal" when `stale` or value is null.
- Consider downstream units: a disconnected monitor must also stop the ECG trace animation and mark the bed in the ward view.
- Detect failures: heartbeat watchdog (T4602), plausibility checks, exception handling around evaluation.
- Preserve state: persist monitor state transitions and last valid reading with timestamps in `devices.monitor_state_log` so restore after recovery is traceable and the event history in the simulation area shows the failure.
- Reference: SD Elements guidance for T347.

**Success Criteria:**
- [ ] Each simulated scenario (low saturation, low battery, sensor fault, connection loss) yields the documented state, output and alarm (unit tests).
- [ ] UI never renders numeric vitals for a stale/disconnected monitor (vitest).
- [ ] An injected exception in evaluation results in an `EVALUATION_ERROR` alarm, not silence.

**Status:** Applied
