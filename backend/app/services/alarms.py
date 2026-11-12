"""Alarm evaluation against configured thresholds.

Acknowledging an alarm does not close a condition that is still occurring: an alarm is only
resolved by the evaluator when the underlying condition has cleared. Acknowledgement is a
separate attribute recorded with who/when, written with a column-scoped conditional UPDATE so it
can never race with (or overwrite) the evaluator's state columns (T205).

Alarm priority scheme (T363, IEC 60601-1-8 inspired; technical alarms are never LOW):

| Condition                                           | Priority |
|-----------------------------------------------------|----------|
| Vital sign outside limits, connection lost (incl. watchdog), evaluation error | high |
| Sensor fault (invalid/implausible data), battery <= 10 %                       | medium |
| Battery <= 20 %                                                                 | low |

Known failure states (T347) - each monitor always resolves to exactly one of these outputs:

| Situation                       | MonitorState  | Vitals shown | Alarm            |
|---------------------------------|---------------|--------------|------------------|
| Normal data                     | online        | values       | per limits       |
| Low battery                     | low_battery   | values       | low_battery      |
| Invalid or implausible reading  | sensor_fault  | blank, stale | sensor_fault     |
| No data / heartbeat too old     | disconnected  | blank, stale | connection_lost  |
| Evaluation raised an exception  | unknown       | blank, stale | evaluation_error |

Fail safe: a parameter without a configured limit, or whose limit row fails its integrity check
(T345), is evaluated against SAFE_DEFAULT_LIMITS instead of being skipped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from psycopg import AsyncConnection

from app.db import fetch_all, fetch_one

log = logging.getLogger("acme.alarms")

LOW_BATTERY_PCT = 20
CRITICAL_BATTERY_PCT = 10
HEARTBEAT_TIMEOUT_SECONDS = 30  # watchdog: no data for this long => connection_lost (6 missed 5 s ticks)

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
ALARM_PRIORITY: dict[str, str] = {
    "low_heart_rate": "high", "high_heart_rate": "high", "low_spo2": "high", "low_resp_rate": "high",
    "high_resp_rate": "high", "low_bp_systolic": "high", "high_bp_systolic": "high",
    "connection_lost": "high", "evaluation_error": "high", "sensor_fault": "medium",
    "low_battery": "low",  # escalated to medium at CRITICAL_BATTERY_PCT
}

# Seeded ward defaults; also the fail-safe limits used when configuration is missing or tampered.
SAFE_DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "heart_rate": (50, 120), "spo2": (92, 100), "resp_rate": (8, 25), "bp_systolic": (90, 160), "bp_diastolic": (50, 100),
}
# Physiologically plausible ranges; values outside are treated as a sensor fault, not as vitals.
PLAUSIBLE: dict[str, tuple[int, int]] = {
    "heart_rate": (20, 300), "spo2": (40, 100), "resp_rate": (2, 80), "bp_systolic": (40, 300), "bp_diastolic": (20, 200),
}


@dataclass(frozen=True)
class Condition:
    type: str
    priority: str
    message: str


class MonitorState(StrEnum):
    ONLINE = "online"
    LOW_BATTERY = "low_battery"
    SENSOR_FAULT = "sensor_fault"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VitalsView:
    """Predefined output contract for the UI: never numeric vitals for a stale/faulty monitor."""
    state: MonitorState
    stale: bool
    heart_rate: int | None = None
    spo2: int | None = None
    resp_rate: int | None = None
    bp_systolic: int | None = None
    bp_diastolic: int | None = None


def is_plausible(reading: dict) -> bool:
    for param, (lo, hi) in PLAUSIBLE.items():
        value = reading.get(param)
        if value is not None and not lo <= value <= hi:
            return False
    return True


def evaluate_vitals(reading: dict, limits: dict[str, tuple[int, int]]) -> list[Condition]:
    """Return active alarm conditions for one reading. Invalid-quality readings never produce vital alarms."""
    if reading.get("quality") == "invalid" or not is_plausible(reading):
        return []
    effective = {**SAFE_DEFAULT_LIMITS, **limits}
    out: list[Condition] = []
    checks = [
        ("heart_rate", "low_heart_rate", "high_heart_rate", "Heart rate"),
        ("spo2", "low_spo2", None, "SpO2"),
        ("resp_rate", "low_resp_rate", "high_resp_rate", "Respiration rate"),
        ("bp_systolic", "low_bp_systolic", "high_bp_systolic", "Systolic BP"),
    ]
    for param, low_type, high_type, label in checks:
        value = reading.get(param)
        if value is None:
            continue
        low, high = effective[param]
        if value < low:
            out.append(Condition(low_type, ALARM_PRIORITY[low_type], f"{label} {value} below limit {low}"))
        elif high_type and value > high:
            out.append(Condition(high_type, ALARM_PRIORITY[high_type], f"{label} {value} above limit {high}"))
    return out


def evaluate_device(battery_pct: int, quality: str | None, connected: bool, plausible: bool = True) -> list[Condition]:
    out: list[Condition] = []
    if not connected:
        out.append(Condition("connection_lost", "high", "Monitor connection lost: no data received"))
        return out
    if quality == "invalid" or not plausible:
        out.append(Condition("sensor_fault", "medium", "Sensor problem: readings are not valid"))
    if battery_pct <= CRITICAL_BATTERY_PCT:
        out.append(Condition("low_battery", "medium", f"Battery critically low ({battery_pct}%)"))
    elif battery_pct <= LOW_BATTERY_PCT:
        out.append(Condition("low_battery", "low", f"Battery low ({battery_pct}%)"))
    return out


EVALUATION_ERROR = Condition("evaluation_error", "high", "Alarm evaluation failed: check the patient directly")


def evaluate_monitor(reading: dict | None, battery_pct: int, limits: dict[str, tuple[int, int]], *,
                     connected: bool, has_patient: bool) -> tuple[VitalsView, list[Condition]]:
    """Single entry point for one monitor tick. Any exception fails safe to an active HIGH alarm."""
    try:
        if not connected or reading is None:
            return VitalsView(MonitorState.DISCONNECTED, stale=True), evaluate_device(battery_pct, None, False)
        plausible = is_plausible(reading)
        conditions = evaluate_device(battery_pct, reading.get("quality"), True, plausible)
        if reading.get("quality") == "invalid" or not plausible:
            return VitalsView(MonitorState.SENSOR_FAULT, stale=True), conditions
        if has_patient:
            conditions += evaluate_vitals(reading, limits)
        state = MonitorState.LOW_BATTERY if battery_pct <= LOW_BATTERY_PCT else MonitorState.ONLINE
        view = VitalsView(state, stale=False, **{k: reading.get(k) for k in PLAUSIBLE})
        return view, conditions
    except Exception as exc:  # fail safe: unknown state is surfaced as an alarm, never as "all normal"
        log.error("alarm_evaluation_failed", extra={"error_type": type(exc).__name__})
        return VitalsView(MonitorState.UNKNOWN, stale=True), [EVALUATION_ERROR]


def monitor_state(status: str, battery_pct: int, last_heartbeat_at: datetime | None, now: datetime,
                  active_types: set[str]) -> dict[str, Any]:
    """Derived, read-only state of a monitor for the devices/live screens (watchdog aware)."""
    age = (now - last_heartbeat_at).total_seconds() if last_heartbeat_at else None
    stale = age is None or age > HEARTBEAT_TIMEOUT_SECONDS
    if status in ("maintenance", "retired"):
        state = status
    elif "evaluation_error" in active_types:
        state = MonitorState.UNKNOWN.value
    elif stale or status == "offline" or "connection_lost" in active_types:
        state = MonitorState.DISCONNECTED.value
    elif "sensor_fault" in active_types:
        state = MonitorState.SENSOR_FAULT.value
    elif battery_pct <= LOW_BATTERY_PCT:
        state = MonitorState.LOW_BATTERY.value
    else:
        state = MonitorState.ONLINE.value
    live = state in (MonitorState.ONLINE.value, MonitorState.LOW_BATTERY.value)
    return {"state": state, "stale": not live, "heartbeat_age_seconds": round(age, 1) if age is not None else None}


# ---------------------------------------------------------------------------
# Threshold integrity (T345)
# ---------------------------------------------------------------------------
def _threshold_payload(row: dict) -> dict:
    updated = row.get("updated_at")
    return {"id": str(row["id"]), "ward_id": str(row["ward_id"]) if row.get("ward_id") else None,
            "patient_id": str(row["patient_id"]) if row.get("patient_id") else None,
            "parameter": str(row["parameter"]), "low": int(row["low_limit"]), "high": int(row["high_limit"]),
            "updated_at": updated.isoformat() if isinstance(updated, datetime) else str(updated)}


def threshold_mac(row: dict) -> str:
    from app.services import integrity

    return integrity.config_mac("alarm_threshold", _threshold_payload(row))


def threshold_trusted(row: dict) -> bool:
    """A row is trusted if its MAC verifies, or if it is unsigned but equal to the safe default."""
    from app.services import integrity

    if integrity.config_mac_valid("alarm_threshold", _threshold_payload(row), row.get("integrity_mac")):
        return True
    return not row.get("integrity_mac") and SAFE_DEFAULT_LIMITS.get(str(row["parameter"])) == (row["low_limit"], row["high_limit"])


async def seal_threshold(conn: AsyncConnection, threshold_id: str) -> None:
    """Recompute the MAC after a legitimate change made through the API (call in the same transaction)."""
    row = await fetch_one(conn, """select id, ward_id, patient_id, parameter::text as parameter, low_limit, high_limit, updated_at
                                   from public.alarm_thresholds where id = %s for update""", (threshold_id,))
    if row is not None:
        await conn.execute("update public.alarm_thresholds set integrity_mac = %s where id = %s", (threshold_mac(row), threshold_id))


async def report_integrity_violation(kind: str, entity_id: str) -> None:
    from app.core.audit import notify_admins
    from app.core.logging import sec_event

    sec_event("config_integrity_violation", outcome="failure", level=logging.ERROR, kind=kind, entity_id=entity_id)
    await notify_admins(f"{kind}_integrity_violation", {"entity_id": entity_id})


async def effective_limits(conn: AsyncConnection, patient_id: str | None, ward_id: str | None) -> dict[str, tuple[int, int]]:
    rows = await fetch_all(
        conn,
        """select id, ward_id, patient_id, parameter::text as parameter, low_limit, high_limit, updated_at, integrity_mac,
                  (patient_id is not null) as is_override
           from public.alarm_thresholds
           where (patient_id = %s) or (ward_id = %s and patient_id is null)""",
        (patient_id, ward_id),
    )
    limits: dict[str, tuple[int, int]] = dict(SAFE_DEFAULT_LIMITS)
    for r in sorted(rows, key=lambda r: r["is_override"]):  # overrides applied last
        if threshold_trusted(r):
            limits[r["parameter"]] = (r["low_limit"], r["high_limit"])
        else:
            # Fail safe: the tampered row is ignored (ward value or safe default stays in force) and admins are alerted.
            await report_integrity_violation("threshold", str(r["id"]))
    return limits


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
async def reconcile(conn: AsyncConnection, monitor_id: str, patient_id: str | None, conditions: list[Condition]) -> dict:
    """Raise new alarms, refresh ongoing ones, and resolve only those whose condition cleared.

    Writes only evaluator columns (state, last_seen_at, resolved_at); acknowledgement columns are untouched."""
    active = await fetch_all(conn, "select id, type::text as type from public.alarms where monitor_id = %s and state = 'active' for update",
                             (monitor_id,))
    active_by_type = {a["type"]: a["id"] for a in active}
    current = {c.type: c for c in conditions}
    raised = resolved = 0
    for ctype, cond in current.items():
        if ctype in active_by_type:
            await conn.execute("update public.alarms set last_seen_at = now() where id = %s", (active_by_type[ctype],))
        else:
            await conn.execute(
                """insert into public.alarms (patient_id, monitor_id, type, priority, message)
                   values (%s, %s, %s::public.alarm_type, %s::public.alarm_priority, %s)
                   on conflict (monitor_id, type) where state = 'active' do update set last_seen_at = now()""",
                (patient_id, monitor_id, ctype, cond.priority, cond.message[:200]),
            )
            raised += 1
    for ctype, alarm_id in active_by_type.items():
        if ctype not in current:
            await conn.execute("update public.alarms set state = 'resolved', resolved_at = now() where id = %s", (alarm_id,))
            resolved += 1
    return {"raised": raised, "resolved": resolved}


ACK_SQL = """update public.alarms set acknowledged_at = now(), acknowledged_by = %s, ack_note = %s
           where id = %s and acknowledged_at is null
           returning id, state::text as state"""


async def acknowledge(conn: AsyncConnection, alarm_id: str, user_id: str, note: str | None) -> dict | None:
    """Record acknowledgement only (atomic, first writer wins). The alarm stays 'active' until the condition clears."""
    return await fetch_one(conn, ACK_SQL, (user_id, note, alarm_id))


async def watchdog_sweep(conn: AsyncConnection, timeout_seconds: int = HEARTBEAT_TIMEOUT_SECONDS) -> list[str]:
    """Raise connection_lost for bound monitors whose heartbeat is older than the timeout (T4602).

    Works for any monitor that silently stops, not only the connection-loss scenario. The SQL
    function also runs from pg_cron so detection does not depend on the API being called."""
    rows = await fetch_all(conn, "select lost_monitor_id::text as monitor_id, alarm_raised from public.watchdog_sweep(%s)",
                           (timeout_seconds,))
    lost = [r["monitor_id"] for r in rows]
    if lost:
        from app.core.logging import sec_event

        sec_event("watchdog_connection_lost", outcome="failure", level=logging.WARNING, monitors=len(lost))
    return lost
