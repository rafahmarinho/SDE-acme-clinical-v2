---
name: t1874-test-that-http-response-headers-do-not-expose-any
description: Tests verifying that ACME Clinical API and SPA responses (success, error and 404) do not expose server software, framework or version details in HTTP response headers.
---

# T1874: Test that HTTP response headers do not expose any sensitive information

**Category:** CODE_FIX
**SD Elements:** [T1874](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1874/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "O sistema médico vai se chamar ACME Clinical. Use Python com FastAPI e Pydantic no backend e"
> (EN: The medical system will be called ACME Clinical. Use Python with FastAPI and Pydantic on the backend and)
> Source: specs/PRD.md, line 17

**What the spec implies (naive approach):**
Without a check, server/framework/version headers (uvicorn, Python version, custom version headers) can appear in responses, especially on error paths that bypass normal handlers.

**Secure Implementation Pattern:**
```python
# backend/tests/test_header_leakage.py
import re
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

FORBIDDEN_NAMES = {"x-powered-by", "x-app-version", "x-process-time", "x-debug", "x-runtime"}
VERSION_RE = re.compile(r"(uvicorn|starlette|fastapi|python|hypercorn)|\d+\.\d+\.\d+", re.I)

@pytest.mark.anyio
@pytest.mark.parametrize("method,path", [("GET", "/api/health"), ("GET", "/api/patients"),
                                         ("GET", "/nope"), ("POST", "/api/alarms/x/ack")])
async def test_no_tech_disclosure(method, path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        r = await c.request(method, path)
    names = {k.lower() for k in r.headers}
    assert not names & FORBIDDEN_NAMES
    for k in ("server", "via"):
        assert not VERSION_RE.search(r.headers.get(k, ""))
    assert "Traceback" not in r.text
```

**Implementation Guidance:**
- Add the pytest above under `backend/tests/`; it verifies the control from T1873, including 401/404/405 paths.
- Manual/post-deploy: `curl -sI https://<api>/api/health` and `curl -sI https://<web>/` and review every header; `server: Vercel` and `x-vercel-id` are platform headers with no version (accepted, documented); anything with a framework name or version number fails.
- Also check that `/docs` and `/openapi.json` are disabled in production and that public source maps are not served (`curl -I https://<web>/assets/index-*.js.map` returns 404).
- Reference: SD Elements guidance for T1874.

**Success Criteria:**
- [ ] `backend/tests/test_header_leakage.py` passes.
- [ ] Manual header review of both deployments finds no software versions.

**Status:** Applied
