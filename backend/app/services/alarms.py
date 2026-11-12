"""Alarm evaluation against configured thresholds.

Acknowledging an alarm does not close a condition that is still occurring: an alarm is only
resolved by the evaluator when the underlying condition has cleared. Acknowledgement is a
separate attribute recorded with who/when.

Priority scheme (highest first): life-threatening vital signs and loss of monitoring
(connection lost) -> high; sensor faults and critically low battery -> medium; low battery -> low.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import AsyncConnection

from app.db import fetch_all, fetch_one

LOW_BATTERY_PCT = 20
CRITICAL_BATTERY_PCT = 10
HEARTBEAT_TIMEOUT_SECONDS = 30  # watchdog: no data for this long => connection_lost

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Condition:
    type: str
    priority: str
    message: str


def evaluate_vitals(reading: dict, limits: dict[str, tuple[int, int]]) -> list[Condition]:
    """Return active alarm conditions for one reading. Invalid-quality readings never produce vital alarms."""
    if reading.get("quality") == "invalid":
        return []
    out: list[Condition] = []
    checks = [
        ("heart_rate", "low_heart_rate", "high_heart_rate", "Heart rate"),
        ("spo2", "low_spo2", None, "SpO2"),
        ("resp_rate", "low_resp_rate", "high_resp_rate", "Respiration rate"),
        ("bp_systolic", "low_bp_systolic", "high_bp_systolic", "Systolic BP"),
    ]
    for param, low_type, high_type, label in checks:
        value = reading.get(param)
        if value is None or param not in limits:
            continue
        low, high = limits[param]
        if value < low:
            out.append(Condition(low_type, "high", f"{label} {value} below limit {low}"))
        elif high_type and value > high:
            out.append(Condition(high_type, "high", f"{label} {value} above limit {high}"))
    return out


def evaluate_device(battery_pct: int, quality: str | None, connected: bool) -> list[Condition]:
    out: list[Condition] = []
    if not connected:
        out.append(Condition("connection_lost", "high", "Monitor connection lost: no data received"))
        return out
    if quality == "invalid":
        out.append(Condition("sensor_fault", "medium", "Sensor problem: readings are not valid"))
    if battery_pct <= CRITICAL_BATTERY_PCT:
        out.append(Condition("low_battery", "medium", f"Battery critically low ({battery_pct}%)"))
    elif battery_pct <= LOW_BATTERY_PCT:
        out.append(Condition("low_battery", "low", f"Battery low ({battery_pct}%)"))
    return out


async def effective_limits(conn: AsyncConnection, patient_id: str | None, ward_id: str | None) -> dict[str, tuple[int, int]]:
    rows = await fetch_all(
        conn,
        """select parameter::text as parameter, low_limit, high_limit, (patient_id is not null) as is_override
           from public.alarm_thresholds
           where (patient_id = %s) or (ward_id = %s and patient_id is null)""",
        (patient_id, ward_id),
    )
    limits: dict[str, tuple[int, int]] = {}
    for r in sorted(rows, key=lambda r: r["is_override"]):  # overrides applied last
        limits[r["parameter"]] = (r["low_limit"], r["high_limit"])
    return limits


async def reconcile(conn: AsyncConnection, monitor_id: str, patient_id: str | None, conditions: list[Condition]) -> dict:
    """Raise new alarms, refresh ongoing ones, and resolve only those whose condition cleared."""
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


async def acknowledge(conn: AsyncConnection, alarm_id: str, user_id: str, note: str | None) -> dict | None:
    """Record acknowledgement only. The alarm stays 'active' until the condition clears."""
    return await fetch_one(
        conn,
        """update public.alarms set acknowledged_at = now(), acknowledged_by = %s, ack_note = %s
           where id = %s and acknowledged_at is null
           returning id, state::text as state""",
        (user_id, note, alarm_id),
    )
