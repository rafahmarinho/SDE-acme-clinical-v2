---
name: t2609-verify-that-the-result-set-size-returned-by-querie
description: Test recipe verifying that ACME Clinical queries for patients, readings, alarms, events and reports are paginated and capped, that clients cannot request unbounded result sets, and that over-limit queries return an error or roll back.
---

# T2609: Verify that the result set size returned by queries are controlled

**Category:** CODE_FIX
**SD Elements:** [T2609](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2609/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: "choose scenarios, advance the simulation, view events and reset the data. The results")
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
Simulated monitors generate continuous readings and events, so tables grow quickly. A naive "view events" or readings history endpoint runs `SELECT * FROM events` or accepts `?limit=1000000`, which can time out the Vercel function, exhaust memory, or dump the full patient dataset in one call.

**Secure Implementation Pattern:**
```python
# backend/app/routers/events.py (control)
from typing import Annotated
from fastapi import Query
MAX_PAGE = 100

@router.get("/simulation/events")
async def list_events(limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
                      cursor: Annotated[str | None, Query(max_length=64)] = None, db=Depends(get_db)):
    rows = await db.fetch(
        "select id, ts, type, monitor_id from events where (%(c)s::timestamptz is null or ts < %(c)s::timestamptz) "
        "order by ts desc limit %(n)s", {"c": cursor, "n": limit + 1})
    return {"items": rows[:limit], "next_cursor": rows[limit - 1]["ts"].isoformat() if len(rows) > limit else None}

# backend/tests/test_result_limits.py
import pytest
@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/patients", "/api/alarms", "/api/simulation/events",
                                  "/api/patients/{pid}/readings"])
async def test_limits(client, admin_headers, seeded_10k_events, patient_id, path):
    url = path.format(pid=patient_id)
    assert (await client.get(url, params={"limit": 100000}, headers=admin_headers)).status_code == 422
    r = await client.get(url, headers=admin_headers)
    assert r.status_code == 200 and len(r.json()["items"]) <= 100
```

**Implementation Guidance:**
- Verify every list query in `backend/app/routers/*.py` and `backend/app/db.py` has a server-enforced `LIMIT` with a bounded `limit` parameter (`le=100`) and cursor/keyset pagination; report exports use bounded date ranges (e.g. max 7 days of readings).
- For Supabase client queries from the frontend, verify `.range()` is used and the project's PostgREST "Max rows" setting is configured as a backstop.
- For sensitive bulk operations (report generation, simulation reset), verify the code counts or checks the affected rows and returns an error / rolls back the transaction if over the limit.
- Seed a large dataset in tests (e.g. 10k events) and confirm responses stay within limits and within the function timeout.
- Reference: SD Elements guidance for T2609.

**Success Criteria:**
- [ ] `backend/tests/test_result_limits.py` passes for all list endpoints.
- [ ] Requests with `limit` above the maximum return 422; default responses return at most 100 items.
- [ ] Report generation over the allowed range returns a clear error and writes nothing.

**Status:** Applied
