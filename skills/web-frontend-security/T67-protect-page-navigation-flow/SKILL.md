---
name: t67-protect-page-navigation-flow
description: Enforces server-side sequencing of ACME Clinical multi-step flows (password recovery, simulation scenario select/advance/reset, binding a monitor to a bed) so out-of-order or replayed requests are rejected regardless of client-side route state.
---

# T67: Protect page navigation flow

**Category:** CODE_FIX
**SD Elements:** [T67](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T67/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados."
> (EN: choose scenarios, advance the simulation, view events and reset the data.)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
A developer would implement step order only in React Router (e.g. scenario screen then "advance" button; bind wizard: pick monitor, pick bed, confirm). Calling the API endpoints directly or out of order (advance with no scenario, confirm binding without a validated selection, reset while another run is active) would then be accepted, corrupting simulation state or binding a monitor to the wrong bed.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql (excerpt): server-side flow state
create type sim_state as enum ('idle', 'scenario_selected', 'running');
create table simulation_runs (
  id uuid primary key default gen_random_uuid(),
  state sim_state not null default 'idle',
  scenario text,
  step int not null default 0,
  updated_by uuid references auth.users, updated_at timestamptz default now()
);
```
```python
# backend/app/services/simulation.py
ALLOWED = {"select": {"idle", "scenario_selected"}, "advance": {"scenario_selected", "running"},
           "reset": {"idle", "scenario_selected", "running"}}
NEXT = {"select": "scenario_selected", "advance": "running", "reset": "idle"}

async def transition(db, run_id: str, action: str, user_id: str, expected_step: int | None = None):
    run = await db.fetch_run_for_update(run_id)          # SELECT ... FOR UPDATE
    if run.state not in ALLOWED[action]:
        raise FlowError(f"'{action}' not allowed in state '{run.state}'")  # -> 409
    if expected_step is not None and expected_step != run.step:
        raise FlowError("Stale or replayed step")          # -> 409
    await db.update_run(run_id, state=NEXT[action],
                        step=run.step + 1 if action == "advance" else 0, updated_by=user_id)
```

**Implementation Guidance:**
- Keep flow state server-side (Supabase tables), never in cookies/localStorage/query strings; the React route is only a view.
- Simulation (`backend/app/routers/simulation.py`, `services/simulation.py`): state machine above; reject out-of-order actions with 409 and require `expected_step` from the client to block replays/double-submits.
- Monitor binding: a single `POST /api/monitors/{id}/bind` with `{bed_id, expected_version}` validated atomically (monitor unbound or owned, bed free, user role nurse/biomedical technician) instead of a multi-request wizard trusting earlier steps.
- Password recovery: rely on Supabase Auth's flow (email link -> `PASSWORD_RECOVERY` event -> `updateUser`); the reset screen in `frontend/src/screens` must only allow `updateUser({ password })` when the `PASSWORD_RECOVERY` session event occurred, and Supabase enforces token single-use and expiry server-side.
- For critical actions, optionally reject steps submitted faster than a human could (e.g. < 300 ms after previous step) and log them.
- Reference: SD Elements guidance for T67.

**Success Criteria:**
- [ ] Advance without a selected scenario, or with a stale `expected_step`, returns 409 and does not change state.
- [ ] Binding is atomic and rejects occupied beds/monitors.
- [ ] Verified by T142 tests.

**Status:** Pending
