# Clinical safety and resilience

Covers T205, T342, T343, T347, T348, T363, T433, T434, T633, T2280, T4602.
Code: `backend/app/services/{alarms,simulation,resilience}.py`, `backend/app/routers/{alarms,simulation}.py`,
`backend/app/core/errors.py`, migration `0004_ops_audit_resilience.sql`. Tests: `backend/tests/test_clinical_safety.py`.

## Priority scheme (T363, T2280)

Every route is classified centrally (`resilience.ROUTE_CLASSES`, test fails on an unclassified route):

| Class | Examples | Shed |
|---|---|---|
| EMERGENCY_SAFETY | alarm list/ack, monitor states, system status, break-glass, auth | never |
| MONITORING | wards, patients, live readings, monitors (GET), simulation advance | never |
| MAIN_FUNCTION | observations, thresholds, monitor binding, maintenance, files | at ≥ 5 DB failures / 30 s |
| SUPERVISORY | reports, staff, settings, audit/events, scenario change, reset | at ≥ 1 DB failure / 30 s; max 5 concurrent per instance |

Alarm priority (IEC 60601-1-8 inspired): vital sign outside limits, connection lost (incl.
watchdog) and evaluation error → **high**; sensor fault and battery ≤ 10 % → **medium**; battery
≤ 20 % → **low**. Technical alarms are never low. Alarms are sorted high → low; the UI uses
distinct colours/sounds per priority.

## Degraded mode (T433, T434)

DB errors (`OperationalError`, pool timeout) return 503 `monitoring_unavailable` with
`Retry-After` and switch the instance to degraded mode for 30 s: supervisory (then main-function)
requests get 503 `degraded_mode`; alarms, acknowledgement, live data and break-glass keep working.
`GET /v1/alarms/system-status` returns `{mode, shed_classes}` without touching the DB, for a
persistent UI banner. Alarm generation is Python-side and independent of Realtime (delivery only);
the SPA falls back Realtime → REST polling → offline banner with last-update time.
Load test of the deployed API (reports burst vs alarm reads) to be recorded per release.

## Known failure states (T347, T348)

`alarms.evaluate_monitor` returns exactly one predefined output per monitor tick:

| Situation | State | Vitals | Alarm |
|---|---|---|---|
| normal | online | values | per limits |
| low battery | low_battery | values | low_battery |
| invalid/implausible reading | sensor_fault | blank, stale | sensor_fault |
| no data / heartbeat too old | disconnected | blank, stale | connection_lost |
| evaluation exception | unknown | blank, stale | evaluation_error (high) |

Unknown ⇒ alarm: missing or tampered limits fall back to safe defaults instead of being skipped.
`GET /v1/alarms/monitor-states` exposes state, `stale` and heartbeat age; the UI must show `--`
and "No signal" for stale monitors. DB outage ⇒ 503 `monitoring_unavailable` ("check patients
directly at the bedside"), never an empty normal-looking screen.

## Critical actions (T342, T343)

| Action | API requirement | Response |
|---|---|---|
| Acknowledge alarm | `acknowledged: true` | `notice`: does not resolve the condition, recorded |
| Change thresholds | `confirm: true` (thresholds router) | audited old/new |
| Bind monitor | `confirm: true` (monitors router) | audited |
| Change scenario | `acknowledged: true` | `notice`: alarms will change, audited |
| Reset demo data | `confirm_text: "RESET DEMO DATA"` + `acknowledged: true` | `notice`: audit preserved |

Requests without the fields are rejected with 422, so the UI dialog cannot be bypassed. The
login system-use notice (authorized staff, fictional data, activity audited) is a frontend
requirement. Government-system clause: not applicable.

## Races, deadlocks, recursion (T205, T633)

* Acknowledgement: single conditional, column-scoped UPDATE (`... where acknowledged_at is null`);
  the evaluator writes only state/last_seen/resolved — an ack can never clear a condition.
* Simulation tick/scenario/reset and the watchdog share one transaction-level advisory lock
  (`acme:simulation`): a concurrent advance gets 409, reset/scenario wait, watchdog skips when busy;
  plus the `version` optimistic check. `lock_timeout = 3s`.
* Lock order: advisory lock → `simulation_state` → `monitors` (FOR UPDATE OF m, by serial) → `alarms`.
* Binding uniqueness: partial unique indexes on active monitor and bed assignments (409).
* Deadlock/lock-timeout: advance is retried up to 3 times with backoff, then 503 `busy`.
* Flow is one-directional: simulator → readings → alarm engine → alarms → Realtime → browser.
  Services never call the API over HTTP; triggers never write to the table they fire on.
* No module-level mutable simulation state: state lives in PostgreSQL.

## Watchdog (T4602)

`public.watchdog_sweep(30)` marks any bound, online monitor whose `last_heartbeat_at` is older than
30 s (6 missed 5 s ticks) as offline and raises a HIGH `connection_lost` alarm — independent of
the simulation scenario. It runs from `pg_cron` every 10 s when the extension is enabled, on every
simulation tick and on alarm/monitor-state reads (best effort, never hides alarms on failure).
When heartbeats resume the monitor returns to online and the condition resolves (history kept).
Note for the demo: if nobody advances the simulation, bound monitors correctly go to
connection_lost after 30 s — the simulation UI should auto-advance while the live view is open.
Simulator stall detection is not applicable (the simulation advances on operator demand).
