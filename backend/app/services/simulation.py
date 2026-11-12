"""Simulated monitor readings (HR, SpO2, respiration, BP, synthetic ECG) and scenarios.

Scenarios: normal, low saturation, low battery, sensor fault, connection loss.

Randomness here produces synthetic physiological data only, so the deterministic, seedable
`random.Random` is appropriate; security-relevant randomness (tokens, secrets, ids) uses
`secrets` / `gen_random_uuid()` elsewhere.

Concurrency: `advance` locks the single simulation_state row (SELECT ... FOR UPDATE) and uses an
optimistic `version` check, so two operators advancing at once cannot interleave ticks.
"""

from __future__ import annotations

import json
import math
import random

from psycopg import AsyncConnection

from app.core.errors import DomainError
from app.db import execute, fetch_all, fetch_one
from app.services import alarms

ECG_SAMPLES = 250  # 1 s at 250 Hz
TICK_SECONDS = 5


def synthetic_ecg(heart_rate: int, rng: random.Random, noisy: bool = False) -> list[float]:
    """Very simplified PQRST waveform, good enough for a demo trace."""
    hr = max(heart_rate, 30)
    period = 250 * 60 / hr
    out = []
    for i in range(ECG_SAMPLES):
        phase = (i % period) / period
        v = 0.1 * math.exp(-((phase - 0.18) ** 2) / 0.0008)        # P
        v -= 0.15 * math.exp(-((phase - 0.36) ** 2) / 0.00005)     # Q
        v += 1.0 * math.exp(-((phase - 0.39) ** 2) / 0.00008)      # R
        v -= 0.25 * math.exp(-((phase - 0.42) ** 2) / 0.00008)     # S
        v += 0.3 * math.exp(-((phase - 0.65) ** 2) / 0.003)        # T
        v += rng.gauss(0, 0.4 if noisy else 0.02)
        out.append(round(v, 3))
    return out


def generate(scenario: str, rng: random.Random, battery_pct: int) -> tuple[dict | None, int]:
    """Return (reading or None when disconnected, new battery level)."""
    drain = 6 if scenario == "low_battery" else 0
    battery = max(0, battery_pct - drain) if drain else min(100, battery_pct)
    if scenario == "connection_loss":
        return None, battery
    hr = int(rng.gauss(78, 4))
    spo2 = int(min(100, rng.gauss(97, 1)))
    rr = int(rng.gauss(15, 1.5))
    sys_bp, dia_bp = int(rng.gauss(122, 6)), int(rng.gauss(78, 4))
    quality = "good"
    if scenario == "low_saturation":
        spo2 = int(rng.uniform(82, 89))
        hr += 15
    if scenario == "sensor_fault":
        quality = "invalid"
        spo2 = None  # type: ignore[assignment]
    reading = {"heart_rate": hr, "spo2": spo2, "resp_rate": rr, "bp_systolic": sys_bp, "bp_diastolic": dia_bp,
               "quality": quality, "ecg": synthetic_ecg(hr, rng, noisy=scenario == "sensor_fault")}
    return reading, battery


async def advance(conn: AsyncConnection, user_id: str, steps: int, expected_version: int) -> dict:
    state = await fetch_one(conn, "select scenario::text as scenario, monitor_scenarios, tick, version "
                                  "from public.simulation_state where id = 1 for update")
    if state is None:
        raise DomainError("Simulation is not initialised.", 500)
    if state["version"] != expected_version:
        raise DomainError("The simulation was changed by someone else. Reload and try again.")

    monitors = await fetch_all(conn, """
        select m.id::text as id, m.battery_pct, m.status::text as status, b.ward_id::text as ward_id,
               p.id::text as patient_id
        from public.monitors m
        left join public.monitor_assignments ma on ma.monitor_id = m.id and ma.unassigned_at is null
        left join public.beds b on b.id = ma.bed_id
        left join public.patients p on p.bed_id = b.id and p.discharged_at is null
        where m.status <> 'retired'
        order by m.serial""")
    overrides: dict = state["monitor_scenarios"] or {}
    totals = {"readings": 0, "raised": 0, "resolved": 0}
    tick = state["tick"]
    for _ in range(steps):
        tick += 1
        for m in monitors:
            scenario = overrides.get(m["id"], state["scenario"])
            rng = random.Random(f"{m['id']}:{tick}")
            reading, battery = generate(scenario, rng, m["battery_pct"])
            m["battery_pct"] = battery
            connected = reading is not None and m["status"] != "maintenance"
            conditions = alarms.evaluate_device(battery, reading["quality"] if reading else None, connected)
            if reading is not None:
                await conn.execute(
                    """insert into public.readings (monitor_id, patient_id, heart_rate, spo2, resp_rate, bp_systolic,
                         bp_diastolic, ecg, quality) values (%s, %s, %s, %s, %s, %s, %s, %s, %s::public.reading_quality)""",
                    (m["id"], m["patient_id"], reading["heart_rate"], reading["spo2"], reading["resp_rate"],
                     reading["bp_systolic"], reading["bp_diastolic"], reading["ecg"], reading["quality"]))
                totals["readings"] += 1
                if m["patient_id"]:
                    limits = await alarms.effective_limits(conn, m["patient_id"], m["ward_id"])
                    conditions += alarms.evaluate_vitals(reading, limits)
            await conn.execute(
                "update public.monitors set battery_pct = %s, last_heartbeat_at = case when %s then now() else last_heartbeat_at end "
                "where id = %s", (battery, connected, m["id"]))
            result = await alarms.reconcile(conn, m["id"], m["patient_id"], conditions)
            totals["raised"] += result["raised"]
            totals["resolved"] += result["resolved"]

    await execute(conn, "update public.simulation_state set tick = %s, version = version + 1, updated_at = now(), updated_by = %s "
                        "where id = 1", (tick, user_id))
    return {"tick": tick, "version": expected_version + 1, **totals}


async def set_scenario(conn: AsyncConnection, user_id: str, scenario: str, monitor_ids: list[str]) -> None:
    if monitor_ids:
        await conn.execute(
            "update public.simulation_state set monitor_scenarios = monitor_scenarios || %s::jsonb, version = version + 1, "
            "updated_at = now(), updated_by = %s where id = 1",
            (json.dumps({mid: scenario for mid in monitor_ids}), user_id))
    else:
        await conn.execute(
            "update public.simulation_state set scenario = %s::public.sim_scenario, monitor_scenarios = '{}'::jsonb, "
            "version = version + 1, updated_at = now(), updated_by = %s where id = 1", (scenario, user_id))


async def reset(conn: AsyncConnection, user_id: str) -> None:
    """Reset demo data to the seeded baseline. The audit trail (events) is intentionally preserved."""
    for sql in ("delete from public.readings", "delete from public.alarms", "delete from public.observations",
                "update public.monitors set battery_pct = 100, status = 'online', last_heartbeat_at = now()"):
        await conn.execute(sql)
    await conn.execute("update public.simulation_state set scenario = 'normal', monitor_scenarios = '{}'::jsonb, tick = 0, "
                       "version = version + 1, updated_at = now(), updated_by = %s where id = 1", (user_id,))
