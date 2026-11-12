---
name: t633-mitigate-deadlock-and-recursion-in-services
description: Avoid deadlocks and recursive call loops among ACME Clinical services (simulation, alarm engine, Realtime notifications, reports, database triggers) through consistent lock ordering, lock timeouts, one-directional asynchronous flows and bounded retries.
---

# T633: Mitigate Deadlock and Recursion in Services

**Category:** CODE_FIX
**SD Elements:** [T633](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T633/)
**Priority:** 4/10 · **Phase:** architecture-design

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: "frontend. The generation of readings, alarms and reports must be done in Python. The")
> Source: specs/PRD.md, line 21

> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: "...password, files and real-time updates. I want the screens working and the data")
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
A tick locks monitors then alarms while an acknowledgement locks alarms then monitors (deadlock). A DB trigger on `alarms` calls an HTTP webhook back into the API, which updates `alarms` again (recursion). The simulation endpoint might call the API's own `/alarms/evaluate` over HTTP from inside the same serverless function.

**Secure Implementation Pattern:**
```python
# backend/app/db.py -- bounded waits and a single documented lock order
LOCK_ORDER = ("devices.monitors", "clinical.patients", "clinical.alarms")  # always acquire in this order

async def tx(conn):
    tr = conn.transaction()
    await tr.start()
    await conn.execute("set local lock_timeout = '2s'; set local statement_timeout = '5s'")
    return tr

async def with_deadlock_retry(fn, attempts: int = 3):
    for i in range(attempts):
        try:
            return await fn()
        except (asyncpg.DeadlockDetectedError, asyncpg.LockNotAvailableError):
            if i == attempts - 1:
                raise HTTPException(503, "Busy, please retry")
            await asyncio.sleep(0.05 * 2 ** i)
```
```sql
-- supabase/migrations: one-directional notification, no trigger recursion
create function clinical.alarm_changed() returns trigger language plpgsql as $$
begin
  if pg_trigger_depth() > 1 then return new; end if;     -- guard against nested firing
  insert into simulation.events(kind, ref_id) values ('alarm.' || tg_op, new.id);  -- buffer
  return new;
end $$;
```

**Implementation Guidance:**
- Draw the execution flow (README diagram): simulator → readings → alarm engine → alarms table → Realtime → browser. Data flows one way; the engine never calls HTTP endpoints of the same API, and services call each other as Python functions, not via HTTP.
- Use Supabase Realtime / an events table as the asynchronous message buffer; consumers (UI, report jobs) read from it rather than being called synchronously.
- Acquire row locks in `LOCK_ORDER` everywhere (`select ... for update` monitors first); keep transactions short; set `lock_timeout` and `statement_timeout`.
- Retry deadlock/lock-timeout errors a bounded number of times with backoff; never retry infinitely.
- Triggers: no trigger updates the table it fires on; guard with `pg_trigger_depth()`; no `pg_net` webhooks back into the API for alarm changes.
- No recursive service functions; recursion in report generation (e.g. nested sections) has a depth limit.
- Reference: SD Elements guidance for T633.

**Success Criteria:**
- [ ] Execution flow diagram documented; static test confirms `services/` never imports an HTTP client targeting the own API.
- [ ] Stress test interleaving ticks, acks and bindings completes with no unhandled deadlock and bounded retries.
- [ ] Trigger recursion test (update in trigger context) terminates.

**Status:** Pending
