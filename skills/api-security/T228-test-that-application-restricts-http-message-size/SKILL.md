---
name: t228-test-that-application-restricts-http-message-size
description: Test that the ACME Clinical API on Vercel rejects HTTP requests exceeding limits on body size, header count/size, request line length and processing time, combining app-level FastAPI limits with documented Vercel platform limits.
---

# T228: Test that application restricts HTTP message size

**Category:** CODE_FIX
**SD Elements:** [T228](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T228/)
**Priority:** 9/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

> "Use Python com FastAPI e Pydantic no backend e"
> (EN: Use Python with FastAPI and Pydantic on the backend and)
> Source: specs/PRD.md, line 17

**What the spec implies (naive approach):**
On Vercel the team does not run Uvicorn or a reverse proxy, so it is easy to assume "the platform handles it" and set no limits. Vercel enforces its own ceilings (for example a 4.5 MB function request body limit and a function `maxDuration`), but those are generic; the app must define and test its own smaller maxima, and the team must know the platform values to test against them.

**Secure Implementation Pattern:**
```python
# backend/app/main.py - app-level header/URL limits (body limit: see T537)
MAX_HEADERS, MAX_HEADER_BYTES, MAX_URL = 50, 8 * 1024, 2048

@app.middleware("http")
async def header_limits(request: Request, call_next):
    raw = request.scope["headers"]
    if len(raw) > MAX_HEADERS or sum(len(k) + len(v) for k, v in raw) > MAX_HEADER_BYTES:
        return JSONResponse({"error": "headers_too_large"}, status_code=431)
    if len(request.url.path) + len(request.url.query) > MAX_URL:
        return JSONResponse({"error": "uri_too_long"}, status_code=414)
    return await call_next(request)

# backend/tests/test_http_limits.py
@pytest.mark.parametrize("case,expected", [
    ({"content": b"x" * (64 * 1024 + 1)}, 413),
    ({"headers": {f"x-h{i}": "a" for i in range(60)}}, 431),
    ({"headers": {"x-big": "a" * 9000}}, 431),
])
async def test_oversized_requests_rejected(api, nurse, case, expected):
    hdrs = {**nurse.auth_header, **case.get("headers", {})}
    r = await api.post("/observations", headers=hdrs, content=case.get("content", b"{}"))
    assert r.status_code == expected

async def test_long_url_rejected(api, nurse):
    assert (await api.get("/patients?q=" + "a" * 3000, headers=nurse.auth_header)).status_code == 414
```

**Implementation Guidance:**
- Record the maxima (step 1 of SD Elements) in the README "Security limits" table: body 64 KB (app), 4.5 MB (Vercel), headers 50 / 8 KB (app), URL 2 KB (app), function `maxDuration` (set explicitly in `backend/vercel.json`, e.g. 10 s), Supabase query `statement_timeout` (e.g. 5 s for the API role). Keep-alive, read timeouts and connection backlog are managed by Vercel's edge; note them as platform-managed and check current Vercel documentation.
- Implement the middleware in `backend/app/main.py`; order it before authentication so invalid messages never reach application logic.
- Tests: `backend/tests/test_http_limits.py` (in-process with httpx) for app limits; a staging script using httpx/JMeter for values just above the Vercel limits and for many concurrent slow requests. Confirm failures are the size errors (`413/414/431`), not unrelated `401`s: send a valid token in every case and check the error body/logs.
- Bound processing time in code too: `asyncio.timeout()` around report generation in `backend/app/services/reports.py`.
- Reference: SD Elements guidance for T228.

**Success Criteria:**
- [ ] Each attribute slightly above its maximum is rejected (no `200`) with the expected status.
- [ ] Rejections happen before the request reaches route handlers (verified via logs).
- [ ] `maxDuration` and DB statement timeout are configured and documented.

**Status:** Pending
