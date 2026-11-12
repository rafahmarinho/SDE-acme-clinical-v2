---
name: t101-test-that-application-is-not-vulnerable-to-sql-inj
description: Security test recipe proving that ACME Clinical search, filters, observations and other inputs that reach Supabase PostgreSQL cannot alter SQL queries (no database errors, no behavioral differences on injected quotes).
---

# T101: Test that application is not vulnerable to SQL injection

**Category:** CODE_FIX
**SD Elements:** [T101](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T101/)
**Priority:** 10/10 · **Phase:** testing

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A developer building patient search, ward/alarm filters and event queries would likely concatenate the search term or sort column into an SQL string in `backend/app/db.py` or the routers (`f"... ILIKE '%{q}%'"`). Without a regression test, a single f-string query can expose all patient records or raise raw PostgreSQL errors to the client.

**Secure Implementation Pattern:**
```python
# backend/tests/test_sql_injection.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

PAYLOADS = ["'", "1'", "' OR '1'='1", "'; DROP TABLE patients;--", "\") OR 1=1--", "1 UNION SELECT null--"]
ENDPOINTS = [
    ("/api/patients", "search"),
    ("/api/alarms", "status"),
    ("/api/simulation/events", "type"),
]

@pytest.mark.asyncio
@pytest.mark.parametrize("path,param", ENDPOINTS)
@pytest.mark.parametrize("payload", PAYLOADS)
async def test_no_sqli(path, param, payload, auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        baseline = await c.get(path, params={param: "zzz-no-match"}, headers=auth_headers)
        r = await c.get(path, params={param: payload}, headers=auth_headers)
    assert r.status_code in (200, 422)
    body = r.text.lower()
    for leak in ("syntax error", "psycopg", "sqlstate", "postgres", "traceback"):
        assert leak not in body
    if r.status_code == 200:  # injected quote must not widen results
        assert len(r.json()["items"]) == len(baseline.json()["items"])
```

**Implementation Guidance:**
- Inventory every endpoint in `backend/app/routers/*.py` that takes query/body values used in a database query (patient search, ward/bed filters, alarm status, event log filters, staff search, report date ranges).
- Send SQL meta-characters (`'`, `"`, `;`, `--`, `/* */`) to each and assert that no database error text or stack trace is returned (relies on the generic handler in `backend/app/core/errors.py`).
- Compare a benign value (`1`) with the tampered value (`1'`): a different result set with no error indicates injection; the test fails in that case.
- The control under test: all queries in `backend/app/db.py` use psycopg parameter binding (`%s` / named params) or the Supabase client query builder; dynamic identifiers (sort columns) come from an allow-list mapping, never from raw input.
- Also add a grep-style CI check that fails on f-strings or `%` formatting inside `execute(` calls.
- Reference: SD Elements guidance for T101.

**Success Criteria:**
- [ ] `backend/tests/test_sql_injection.py` covers every list/search/filter endpoint with the payload set above and passes.
- [ ] No response contains PostgreSQL/psycopg error text; injected payloads return 422 or the same result count as a non-matching baseline.
- [ ] CI static check finds zero string-built SQL statements in `backend/app`.

**Status:** Pending
