---
name: t2600-control-the-result-set-size-returned-by-a-query
description: Cap the number of rows ACME Clinical queries return (patient, reading, alarm, event, staff lists and audit/CSV reports) with bounded LIMIT/OFFSET, server-side maximums and an explicit error when a report would exceed its row limit, including PostgREST max_rows for direct Supabase access.
---

# T2600: Control the result set size returned by a query

**Category:** CODE_FIX
**SD Elements:** [T2600](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T2600/)
**Priority:** 7/10 · **Phase:** development

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: services and database access. Include login, password recovery, profile, settings, search, filters, loading states and error messages. Adapt navigation to user profiles)
> Source: specs/PRD.md, lines 11-13

**What the spec implies (naive approach):**
Search, filters, events and reports are typically implemented as "fetch all matching rows". Readings accumulate every tick for ten monitors, and events/audit rows grow without bound, so an unfiltered query or a `limit=1000000` parameter returns huge result sets: memory exhaustion in the function, slow pages, and bulk exfiltration of PHI in a single call.

**Secure Implementation Pattern:**
```python
# backend/app/schemas/__init__.py
MAX_PAGE_SIZE = 100
MAX_OFFSET = 10_000
def bounded_int(lo: int, hi: int):
    return Annotated[int, Field(ge=lo, le=hi)]

# backend/app/services/reports.py
MAX_AUDIT_ROWS = 10_000

class ResultTooLarge(DomainError):
    status_code = 422; code = "result_too_large"
    message = "The selected range returns too many rows. Narrow the date range or filters."

async def audit_rows(conn, start, end, actions=()):
    rows = await fetch_all(conn,
        "select ... from public.events where occurred_at >= %s and occurred_at < %s "
        "and (%s::text[] = '{}' or action = any(%s)) order by id limit %s",
        (start, end, list(actions), list(actions), MAX_AUDIT_ROWS + 1))     # fetch one extra to detect overflow
    if len(rows) > MAX_AUDIT_ROWS:
        raise ResultTooLarge()                                               # no silent truncation of reports
    return rows
```
```toml
# supabase/config.toml - caps rows returned by PostgREST to direct (anon/authenticated) clients
[api]
max_rows = 200
```

**Implementation Guidance:**
- All list endpoints (`backend/app/routers/{patients,alarms,events,staff,files,monitors,maintenance}.py`) take `limit`/`offset` bounded by `MAX_PAGE_SIZE`/`MAX_OFFSET` and always issue `LIMIT` in SQL, including the defaults.
- Readings for live charts are capped (`MAX_READINGS` in `backend/app/routers/patients.py`) and time-windowed.
- Reports and CSV exports (`backend/app/services/reports.py`) use the "limit + 1" check and raise an explicit error (do not silently truncate); bound date ranges.
- Set `[api] max_rows` in `supabase/config.toml` for any direct Supabase client reads from `frontend/src/services/api.ts`, and use `.range()` in the frontend.
- Set `statement_timeout` for the API role so runaway queries roll back (T35).
- Reference: SD Elements guidance for T2600.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_api_security.py`): `?limit=1000` -> 422; default list call issues SQL with `LIMIT` (assert on captured query).
- [ ] Pytest: audit report over a range with `MAX_AUDIT_ROWS + 1` rows returns 422 `result_too_large`.
- [ ] `supabase/config.toml` has an explicit `max_rows`.

**Status:** Pending
