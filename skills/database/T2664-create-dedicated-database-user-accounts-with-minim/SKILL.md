---
name: t2664-create-dedicated-database-user-accounts-with-minim
description: Use a separate, single-purpose database account for each ACME Clinical consumer (API, simulation engine, demo reset, migrations, reporting) in Supabase PostgreSQL, each with only the privileges its use requires.
---

# T2664: Create dedicated database user accounts with minimum privileges (Database Server)

**Category:** CODE_FIX
**SD Elements:** [T2664](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2664/)
**Priority:** 8/10 · **Phase:** deployment

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: "choose scenarios, advance the simulation, view events and reset the data. The results")
> Source: specs/PRD.md, line 43

> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: "...complete code, database configuration, initial data, environment variable examples and a")
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
"Reset the data" needs TRUNCATE/DELETE, and the simulator writes readings constantly, so a developer would give one all-powerful account to everything. Then a bug in a read-only report endpoint has the same power as the reset.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0002_app_roles.sql (continued)
create role acme_sim_rw nologin;
create role acme_simulator login nosuperuser nobypassrls in role acme_sim_rw;  -- readings/events only
-- password set out-of-band (dashboard / CLI), never committed
grant usage on schema clinical, simulation to acme_sim_rw;
grant insert on clinical.vital_readings, simulation.events to acme_sim_rw;
grant select, update (status, battery_pct, last_heartbeat_at) on devices.monitors to acme_sim_rw;

create role acme_reset_owner nologin;                     -- owns only the reset function
grant delete, insert on clinical.vital_readings, clinical.alarms, clinical.observations,
      simulation.events to acme_reset_owner;

create function simulation.reset_demo_data(p_actor uuid) returns void
  language plpgsql security definer set search_path = '' as $$
begin
  delete from clinical.alarms; delete from clinical.vital_readings;
  delete from clinical.observations; delete from simulation.events;
  perform simulation.load_seed();                         -- 12 patients, 10 monitors
  insert into audit.events(action, actor_id) values ('simulation.reset', p_actor);
end $$;
alter function simulation.reset_demo_data(uuid) owner to acme_reset_owner;
revoke execute on function simulation.reset_demo_data(uuid) from public;
grant execute on function simulation.reset_demo_data(uuid) to acme_api_rw;  -- API checks SIM_RESET first
```

**Implementation Guidance:**
- Accounts, one purpose each: `acme_api` (request handling), `acme_simulator` (Python simulation ticks in `backend/app/services/simulation.py`), `acme_reset_owner` (owns the reset function, never logs in), `postgres` (migrations only, from CI/CLI), optional `acme_reporting` (read-only views).
- Grant per schema/table only what each needs; no account gets DDL; reset is exposed only as a SECURITY DEFINER function with fixed `search_path`.
- Apply permissions via group roles (T2597), not directly on login roles.
- Provide separate env vars in `backend/.env.example` (`DATABASE_URL`, `SIMULATOR_DATABASE_URL`) and never reuse the `postgres` password.
- If the simulator runs inside the same Vercel function, still use its own connection pool with the simulator account.
- Reference: SD Elements guidance for T2664.

**Success Criteria:**
- [ ] Each account appears in `\du+` with a documented single purpose.
- [ ] `acme_simulator` cannot read `clinical.observations` or modify thresholds (pgTAP).
- [ ] Reset works only through `simulation.reset_demo_data` and writes an audit row.

**Status:** Applied
