---
name: t38-bind-variables-in-sql-statements
description: Bind every variable in ACME Clinical SQL (psycopg queries in the FastAPI backend, PL/pgSQL functions in Supabase migrations) instead of concatenating untrusted data, and use psycopg.sql identifiers or allowlists for dynamic column/sort names.
---

# T38: Bind variables in SQL statements

**Category:** CODE_FIX
**SD Elements:** [T38](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T38/)
**Priority:** 10/10 · **Phase:** development

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: services and database access. Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Patient search, filters (ward, alarming, date ranges), sort order and report periods are easiest to implement with f-strings: `f"... where name ilike '%{q}%' order by {sort}"`. That is classic SQL injection against a database holding PHI, executed with the API role's privileges. Dynamic SQL inside PL/pgSQL functions (`execute 'select ... ' || p_input`) has the same flaw.

**Secure Implementation Pattern:**
```python
# backend/app/routers/patients.py (using helpers in backend/app/db.py)
from psycopg import sql

SORTS = {"name": sql.Identifier("display_name"), "bed": sql.Identifier("bed_label"),
         "admitted": sql.Identifier("admitted_at")}

async def list_patients(conn, q: str | None, ward_id: UUID | None, sort: str, limit: int, offset: int):
    order_col = SORTS.get(sort, SORTS["name"])                    # identifiers from an allowlist
    query = sql.SQL("""
        select id, display_name, bed_label, ward_id from public.patients
        where (%(ward)s::uuid is null or ward_id = %(ward)s)
          and (%(q)s::text is null or display_name ilike '%%' || %(q)s || '%%')
        order by {col} limit %(limit)s offset %(offset)s""").format(col=order_col)
    return await fetch_all(conn, query, {"ward": ward_id, "q": escape_like(q), "limit": limit, "offset": offset})

def escape_like(q: str | None) -> str | None:
    return None if q is None else q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```
```sql
-- supabase/migrations: dynamic SQL in plpgsql uses format() with %I / %L or USING
execute format('delete from public.%I where created_at < $1', p_table) using p_cutoff;
```

**Implementation Guidance:**
- All database access goes through `backend/app/db.py` (`fetch_all`, `fetch_one`, `execute`) with `params`; the `sql` argument must be a literal or a `psycopg.sql.Composed` object, never an f-string/`%`/`+` containing request data.
- Column, table and sort names come from dictionaries of `sql.Identifier` (routers `patients.py`, `alarms.py`, `events.py`, `reports.py`); unknown values fall back to a default or return 422 via Pydantic `Literal` types in `backend/app/schemas/__init__.py`.
- Escape `LIKE` wildcards in search terms; bind `limit`/`offset` values (bounded by `MAX_PAGE_SIZE`/`MAX_OFFSET`).
- In `supabase/migrations/*.sql`, PL/pgSQL `execute` must use `format('%I', ...)`/`%L` or `USING`; prefer static SQL.
- Supabase JS calls in `frontend/src/services/api.ts` use the query builder (parameterised); never build PostgREST `or=` filter strings from raw user text.
- Reference: SD Elements guidance for T38.

**Success Criteria:**
- [ ] `grep -rnE "(execute|fetch_all|fetch_one)\(conn, f\"" backend/app` and `grep -rn "\.format(" backend/app/routers` find no SQL built from input.
- [ ] Pytest (`backend/tests/test_input_validation.py`): search `q="' or 1=1 --"` and `sort="name; drop table patients"` return 200/422 with no extra rows and no SQL error.
- [ ] Every `execute` in `supabase/migrations` uses `format` with `%I/%L` or `USING`.

**Status:** Pending
