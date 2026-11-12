---
name: t4602-utilize-watchdog-timers-to-ensure-devices-can-quic
description: Use heartbeat watchdogs so ACME Clinical quickly detects unresponsive simulated monitors, a stalled simulation engine or a dead live-data feed, raising connection-loss technical alarms, blanking stale vitals and recovering automatically.
---

# T4602: Utilize watchdog timers to ensure devices can quickly detect whether a system is unresponsive

**Category:** CODE_FIX
**SD Elements:** [T4602](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T4602/)
**Priority:** 7/10 · **Phase:** architecture-design

**Spec Context:**
> "acontecendo. Simule leituras normais, saturação baixa, bateria fraca, problema no sensor e"
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...happening. Simulate normal readings, low saturation, low battery, sensor problem and connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, lines 37-39

**What the spec implies (naive approach):**
"Connection loss" would be simulated only as a scenario flag. A monitor that genuinely stops sending (or a stalled simulator, since Vercel functions are not long-running) would leave the last values on screen with no alarm. Simulated monitors are software, so "reset the device" means marking it disconnected and attempting reconnection, not a hardware reboot.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0006_watchdog.sql  (pg_cron on Supabase; runs independently of Vercel)
create function devices.watchdog_sweep() returns void language plpgsql security definer set search_path = '' as $$
begin
  with lost as (
    update devices.monitors m set status = 'disconnected'
     where m.status <> 'disconnected' and m.bed_id is not null
       and m.last_heartbeat_at < now() - interval '15 seconds'
    returning m.id, m.bed_id)
  insert into clinical.alarms (monitor_id, bed_id, code, priority, condition_active, kind)
  select id, bed_id, 'CONNECTION_LOST', 'high', true, 'technical' from lost
  on conflict (monitor_id, code) where condition_active do nothing;

  -- watchdog for the simulator itself
  if (select max(created_at) from simulation.events where kind = 'tick') < now() - interval '60 seconds' then
    insert into simulation.events(kind) values ('watchdog.simulator_stalled');
  end if;
end $$;
select cron.schedule('acme-watchdog', '10 seconds', 'select devices.watchdog_sweep()');
```
```ts
// frontend/src/hooks/useStaleWatchdog.ts -- client-side watchdog on the live feed
export function useStaleWatchdog(lastUpdateAt: number, timeoutMs = 10_000) {
  const [stale, setStale] = useState(false);
  useEffect(() => {
    const t = setInterval(() => setStale(Date.now() - lastUpdateAt > timeoutMs), 1_000);
    return () => clearInterval(t);
  }, [lastUpdateAt, timeoutMs]);
  return stale;   // VitalTile shows "--" and "No signal" when true
}
```

**Implementation Guidance:**
- Monitor heartbeat: each simulated monitor updates `last_heartbeat_at` on every reading (in `backend/app/services/simulation.py`); the connection-loss scenario simply stops heartbeats so the real watchdog path is exercised.
- Timeouts: monitor 15 s (≈ 3 missed 5 s readings), simulator 60 s, browser feed 10 s; keep them in `backend/app/core/config.py` and document the rationale.
- Run the sweep where it does not depend on the API being up: Supabase `pg_cron` (sub-minute schedules supported), with Vercel Cron as a secondary trigger if desired.
- Recovery ("reset"): when heartbeats resume, set status `online`, mark the CONNECTION_LOST condition inactive (alarm history kept); the alarm only clears when the condition ends, not when acknowledged.
- Show the watchdog state in the devices screen for biomedical technicians, and log transitions for maintenance tracking.
- Test the watchdog regularly (T348 scenarios) with frozen time.
- Reference: SD Elements guidance for T4602.

**Success Criteria:**
- [ ] Stopping heartbeats for a bound monitor creates a HIGH `CONNECTION_LOST` technical alarm within 25 s.
- [ ] Browser shows "No signal" within 10 s of the last update when the feed stalls (vitest with fake timers).
- [ ] Resumed heartbeats return the monitor to `online` and end the condition; a simulator stall raises a watchdog event.

**Status:** Pending
