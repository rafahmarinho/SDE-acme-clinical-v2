---
name: t1873-prevent-information-leakage-through-http-response
description: Removes or neutralizes HTTP response headers that reveal server technology or versions (Server, X-Powered-By, framework/version headers, debug headers) from the ACME Clinical FastAPI API and the Vercel-hosted SPA, and keeps error responses generic.
---

# T1873: Prevent information leakage through HTTP response headers

**Category:** CODE_FIX
**SD Elements:** [T1873](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1873/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "O sistema médico vai se chamar ACME Clinical. Use Python com FastAPI e Pydantic no backend e"
> (EN: The medical system will be called ACME Clinical. Use Python with FastAPI and Pydantic on the backend and)
> Source: specs/PRD.md, line 17

**What the spec implies (naive approach):**
A FastAPI app run locally with uvicorn emits `server: uvicorn`; developers often add `X-Process-Time`, `X-App-Version` or debug headers, and libraries may add `X-Powered-By`. These reveal the stack and versions, helping attackers pick known exploits.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
from starlette.middleware.base import BaseHTTPMiddleware

LEAKY = ("server", "x-powered-by", "x-aspnet-version", "x-runtime",
         "x-app-version", "x-process-time", "x-debug", "via")

class StripLeakyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for h in LEAKY:
            if h in response.headers:
                del response.headers[h]
        return response

# backend/app/main.py
app = FastAPI(
    title="ACME Clinical API",
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None, openapi_url=None if settings.environment == "production" else "/openapi.json",
)
app.add_middleware(StripLeakyHeadersMiddleware)
# local dev: uvicorn app.main:app --no-server-header
```

**Implementation Guidance:**
- Register `StripLeakyHeadersMiddleware` in `backend/app/main.py` and never add version/timing headers in `backend/app/routers/*`.
- Run uvicorn locally with `--no-server-header` (and `--no-date-header` optional) in README/dev scripts.
- Vercel adds `server: Vercel` and `x-vercel-id`/`x-vercel-cache` at the edge; these identify the hosting platform (already public via DNS) but not versions, and cannot be removed from app code. Document this as an accepted platform header.
- In `backend/app/core/errors.py`, return generic error JSON (`{"detail": "Internal error", "request_id": ...}`) without stack traces or library names; disable OpenAPI docs in production or protect them.
- In `frontend/vercel.json` do not add custom headers exposing build versions; do not ship source maps publicly (`build.sourcemap: false` or `"hidden"` in `vite.config.ts`).
- Reference: SD Elements guidance for T1873.

**Success Criteria:**
- [ ] API responses contain no `x-powered-by`, version or debug headers; local dev contains no `server: uvicorn`.
- [ ] Production OpenAPI docs are disabled or require auth; 500 responses carry no stack trace.
- [ ] Verified by T1874 tests.

**Status:** Applied
