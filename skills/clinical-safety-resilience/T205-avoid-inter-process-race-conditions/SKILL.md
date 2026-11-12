---
name: t205-avoid-inter-process-race-conditions
description: Prevent race conditions in ACME Clinical between simulation ticks, alarm evaluation, alarm acknowledgements, monitor-to-bed binding and data reset across concurrent Vercel function instances, using atomic SQL updates, row locks, advisory locks and no shared mutable globals.
---

# T205: Avoid inter-process race conditions

**Category:** CODE_FIX
**SD Elements:** [T205](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T205/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow binding a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

> "acompanhar manutenção. Reconhecer um alarme não encerra uma condição que ainda está"
> (EN: "...track maintenance. Acknowledging an alarm does not end a condition that is still")
> Source: specs/PRD.md, line 35

**What the spec implies (naive approach):**
A simulation tick reads an alarm, decides it is still active, and writes the whole row back while a nurse's acknowledgement lands in between — the ack is lost, or worse, the ack handler's write clears the active condition. Two "advance simulation" clicks or a reset during a tick can interleave across Vercel instances. Module-level dicts holding simulation state are not shared between serverless instances anyway.

**Secure Implementation Pattern:**
```python
# backend/app/services/alarms.py -- column-scoped atomic updates; ack never touches condition
async def acknowledge(conn, alarm_id: UUID, user: CurrentUser, note: str | None):
    row = await conn.fetchrow("""
        update clinical.alarms
           set acknowledged_at = now(), acknowledged_by = $2, ack_note = $3,
               silenced_until = now() + interval '2 minutes'
         where id = $1 and acknowledged_at is null
        returning id, condition_active, version""", alarm_id, user.id, note)
    if row is None:
        raise HTTPException(409, "Alarm already acknowledged or not found")
    return row                       # condition_active stays as the engine set it

# backend/app/services/simulation.py -- one tick at a time across all instances
async def advance(pool, steps: int, actor: CurrentUser):
    async with pool.acquire() as conn, conn.transaction():
        if not await conn.fetchval("select pg_try_advisory_xact_lock(hashtext('acme:sim_tick'))"):
            raise HTTPException(409, "Simulation step already in progress")
        for _ in range(min(steps, 60)):
            readings = generate_readings(await load_sim_state(conn))     # pure function, no globals
            await conn.executemany(INSERT_READING, readings)
            await conn.execute("""
                update clinical.alarms a set condition_active = e.active, last_evaluated_at = now(),
                       version = a.version + 1
                  from unnest($1::uuid[], $2::bool[]) as e(id, active) where a.id = e.id""",
                *evaluate_all(readings))
```

**Implementation Guidance:**
- Identify concurrent areas: simulation advance/ticks, alarm evaluation vs acknowledgement, monitor-to-bed binding (two technicians binding the same monitor), simulation reset vs tick, report generation reading while reset runs.
- No shared mutable module globals or singletons for simulation state in `backend/app/services/simulation.py`; state lives in PostgreSQL and is passed explicitly. Constants are immutable (`Final`, frozen dataclasses).
- Use single-statement conditional updates (`... where acknowledged_at is null`) and column-scoped writes so the engine updates `condition_active` and the ack updates only ack columns.
- Serialize ticks and reset with the same transaction-level advisory lock; reset waits (`pg_advisory_xact_lock`) rather than racing.
- Enforce binding uniqueness with constraints: `unique (monitor_id) where unbound_at is null` and `unique (bed_id) where unbound_at is null`; handle `UniqueViolation` as 409.
- Use `async with` / `try/finally` so locks and transactions are always released (FastAPI is async; avoid blocking calls inside locks).
- Reference: SD Elements guidance for T205.

**Success Criteria:**
- [ ] Concurrency test (asyncio.gather of 50 acks + ticks) never loses an acknowledgement and never sets `condition_active=false` from an ack.
- [ ] Two concurrent `advance` calls: one succeeds, one gets 409; reset during a tick waits and completes consistently.
- [ ] Concurrent binding of the same monitor to two beds yields exactly one success.

**Status:** Applied
