---
name: t1542-use-the-correct-http-methods-for-making-state-chan
description: Design the ACME Clinical API so every state change (alarm acknowledgement, monitor-to-bed binding, observations, thresholds, simulation advance/reset, logout) uses POST, PATCH or DELETE, and GET/HEAD are strictly read-only.
---

# T1542: Use the correct HTTP methods for making state-changing operations

**Category:** CODE_FIX
**SD Elements:** [T1542](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T1542/)
**Priority:** 7/10 · **Phase:** architecture-design

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados."
> (EN: choose scenarios, advance the simulation, view events and reset the data.)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
Action-style features are often wired as links: `GET /alarms/42/ack`, `GET /simulation/advance`, `GET /simulation/reset?scenario=low_spo2`, `GET /logout`. Such GETs can be triggered by prefetching, crawlers, browser history, `<img>` tags or a shared link, resetting demo data or acknowledging a real alarm without intent; they also defeat CSRF defences that assume GET is safe.

**Secure Implementation Pattern:**
```python
# backend/app/routers/*.py  - method map
# GET    /wards, /patients, /patients/{id}, /alarms, /devices, /simulation/events   (read-only)
# POST   /alarms/{id}/acknowledge        -> 201 creates an acknowledgement (condition stays active)
# PUT    /beds/{bed_id}/monitor  (or POST /bed-assignments) -> bind monitor to bed
# DELETE /beds/{bed_id}/monitor          -> unbind
# POST   /patients/{id}/observations     -> record observation
# PATCH  /thresholds/{id}                -> change limits
# POST   /simulation/scenario | /simulation/advance | /simulation/reset
# POST   /maintenance/tickets ; PATCH /maintenance/tickets/{id}
# POST   /auth/logout

@router.post("/alarms/{alarm_id}/acknowledge", response_model=AckOut, status_code=201)
async def acknowledge(alarm_id: int, body: AckIn, sess=Depends(require_role("nurse", "physician"))):
    return await alarms.acknowledge(alarm_id, sess.user_id, body.note)   # does not clear the condition

# backend/tests/test_http_methods.py
def test_get_routes_are_read_only(app):
    for r in app.routes:
        if isinstance(r, APIRoute) and r.methods & {"GET", "HEAD"}:
            assert not r.methods & {"POST", "PUT", "PATCH", "DELETE"}, r.path
            assert not re.search(r"(ack|reset|advance|logout|delete|bind|create|update)", r.path), r.path
```

**Implementation Guidance:**
- Apply the method map above to `backend/app/routers/{alarms,monitors,observations,thresholds,simulation,maintenance,auth}.py`; if `PUT` is used for binding, add it to the T65 allow-list and CORS methods.
- GET handlers must not write: no "mark as read", no lazy creation, no audit rows written by GET other than access logs. Report generation that persists a file is `POST /reports` and then `GET /reports/{id}` to download.
- Use the DB as a second guard: run GET handlers in a read-only transaction (`SET TRANSACTION READ ONLY`) in `backend/app/db.py`, so an accidental write raises an error in tests.
- Frontend (`frontend/src/services/*`): actions are buttons that call `api.post/patch/delete`, never `<a href>` to an action URL.
- Add `backend/tests/test_http_methods.py`: static check above, plus runtime check that `GET` on every action path returns `405`, and that each GET leaves row counts in `alarm_acknowledgements`, `observations`, `simulation_events` unchanged.
- Reference: SD Elements guidance for T1542.

**Success Criteria:**
- [ ] No GET/HEAD route changes server state (static and runtime tests pass).
- [ ] Logout, alarm acknowledgement, binding, observations, thresholds and simulation actions use POST/PUT/PATCH/DELETE.
- [ ] GET handlers run in read-only transactions.

**Status:** Applied
