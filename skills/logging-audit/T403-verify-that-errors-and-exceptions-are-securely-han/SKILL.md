---
name: t403-verify-that-errors-and-exceptions-are-securely-han
description: Tests that ACME Clinical API and UI error responses are generic, come from the central catalogue, never expose stack traces, SQL or Supabase internals, and do not enable user enumeration.
---

# T403: Verify that errors and exceptions are securely handled

**Category:** CODE_FIX
**SD Elements:** [T403](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T403/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: filters, loading states and error messages. Adapt navigation to the user profiles)
> Source: specs/PRD.md, line 13

**What the spec implies (naive approach):**
Error messages are checked only for being displayed, not for content. Leaks such as PostgREST error text, Python tracebacks from Vercel functions or distinct login failure messages would pass unnoticed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_error_handling.py
import re, pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from app.main import app

LEAK = re.compile(r"(?i)traceback|File \"|/var/task|psycopg|postgrest|syntax error|SELECT |relation \"|supabase")

boom = APIRouter()
@boom.get("/__test_boom")
async def _boom(): raise RuntimeError("relation \"patients\" does not exist")
app.include_router(boom)

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,kw", [
    ("get", "/__test_boom", {}),
    ("get", "/patients/not-a-uuid", {}),
    ("post", "/observations", {"content": b"{bad json"}),
    ("get", "/does-not-exist", {}),
])
async def test_errors_are_generic(method, path, kw, nurse_token):
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t") as c:
        r = await c.request(method, path, headers={"Authorization": f"Bearer {nurse_token}"}, **kw)
    assert r.status_code >= 400 and not LEAK.search(r.text)
    assert set(r.json()) <= {"error", "message", "error_id", "fields"}

@pytest.mark.asyncio
async def test_no_user_enumeration():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        a = await c.post("/auth/login", json={"email": "nobody@acme.test", "password": "x"})
        b = await c.post("/auth/login", json={"email": "nurse@acme.test", "password": "wrong"})
    assert (a.status_code, a.json()) == (b.status_code, b.json())
```

**Implementation Guidance:**
- Confirm with code review that `core/errors.py` registers a global `Exception` handler and that messages come from a single catalogue.
- Trigger: unhandled exception, malformed JSON, invalid UUID, unknown route, 405, DB constraint violation, Storage upload failure, expired JWT. Check bodies and headers for traces, paths (`/var/task` on Vercel), SQL, library names.
- Verify login and password recovery responses are identical for existing/non-existing accounts (also if the frontend calls Supabase Auth directly — check the UI message).
- Manual check against the deployed Vercel API with a proxy (Burp/DevTools).
- No remote system needs detailed errors in this design; note that signed/encrypted detailed errors are not applicable.
- Reference: SD Elements guidance for T403.

**Success Criteria:**
- [ ] `backend/tests/test_error_handling.py` passes.
- [ ] Manual check of deployed API documented with no leaks.
- [ ] Frontend vitest asserts the error component shows only catalogue text and error ID.

**Status:** Pending
