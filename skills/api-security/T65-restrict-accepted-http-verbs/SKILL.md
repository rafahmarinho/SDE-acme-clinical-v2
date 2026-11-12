---
name: t65-restrict-accepted-http-verbs
description: Restrict the ACME Clinical FastAPI API to the HTTP methods each route actually needs (GET, POST, PATCH, DELETE, plus CORS OPTIONS), reject everything else with 405, disallow method-override headers, and keep the CORS method list explicit.
---

# T65: Restrict accepted HTTP verbs

**Category:** CODE_FIX
**SD Elements:** [T65](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T65/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Use Python com FastAPI e Pydantic no backend e"
> (EN: Use Python with FastAPI and Pydantic on the backend and)
> Source: specs/PRD.md, line 17

**What the spec implies (naive approach):**
FastAPI already answers `405` for undeclared methods on a known path, but common shortcuts widen the surface: `@app.api_route(..., methods=["GET","POST","PUT","DELETE"])` catch-alls, CORS configured with `allow_methods=["*"]`, middleware honouring `X-HTTP-Method-Override`, and the SPA rewrite in Vercel forwarding any verb. TRACE/CONNECT or arbitrary verbs should never reach the app.

**Secure Implementation Pattern:**
```python
# backend/app/main.py
app = FastAPI(docs_url=None if settings.env == "production" else "/docs",
              redoc_url=None, openapi_url=None if settings.env == "production" else "/openapi.json")
ALLOWED_METHODS = {"GET", "HEAD", "POST", "PATCH", "DELETE", "OPTIONS"}

@app.middleware("http")
async def method_allowlist(request: Request, call_next):
    if request.method not in ALLOWED_METHODS:
        return JSONResponse({"error": "method_not_allowed"}, status_code=405,
                            headers={"Allow": ", ".join(sorted(ALLOWED_METHODS - {"HEAD"}))})
    if any(h in request.headers for h in ("x-http-method-override", "x-http-method", "x-method-override")):
        return JSONResponse({"error": "method_override_not_supported"}, status_code=400)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],          # exact Vercel/custom domain, no "*"
    allow_methods=["GET", "POST", "PATCH", "DELETE"],   # explicit, no "*"
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Session-Expires-At", "Retry-After"],
)
```

**Implementation Guidance:**
- Declare each route with a single specific decorator (`@router.get`, `@router.post`, `@router.patch`, `@router.delete`) in `backend/app/routers/*.py`; do not use `api_route` with method lists. `PUT` is not needed if updates use `PATCH`; leave it out of the allow-list unless a route requires it.
- Add the allow-list middleware and explicit CORS configuration in `backend/app/main.py`, outermost so unknown verbs are rejected before auth and routing.
- Do not add `HEAD` handlers unless needed (FastAPI does not create them automatically for `@router.get`); if added, they must use the same auth dependency as `GET`.
- Disable or protect `/docs` and `/openapi.json` in production.
- Map routes to verbs according to T1542 (state changes never via `GET`).
- Reference: SD Elements guidance for T65.

**Success Criteria:**
- [ ] `TRACE`, `CONNECT`, `PUT` (unless needed) and random verbs return `405` on all paths.
- [ ] Method-override headers are rejected.
- [ ] CORS preflight advertises only the explicit method list and origin.
- [ ] Verified by T113 tests.

**Status:** Applied
