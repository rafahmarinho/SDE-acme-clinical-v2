---
name: t64-set-no-cache-for-confidential-web-pages
description: Ensures ACME Clinical API responses carrying patient data (vitals, observations, alarms, reports) and the authenticated SPA shell are sent with no-store caching headers so browsers, proxies and the Vercel edge never retain confidential clinical data.
---

# T64: Set no-cache for confidential web pages

**Category:** CODE_FIX
**SD Elements:** [T64](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T64/)
**Priority:** 4/10 · **Phase:** development

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
A developer would build FastAPI JSON endpoints for patients, readings, alarms and reports and let Vercel apply its default caching. Without explicit headers, browsers (bfcache/disk cache) or intermediary caches may store patient detail and report responses, so another user on a shared nursing-station workstation could later see them. Report downloads from Supabase Storage are also cacheable by default.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

NO_STORE = {
    "Cache-Control": "no-store, no-cache, max-age=0, must-revalidate, private",
    "Pragma": "no-cache",
    "Expires": "0",
}

class NoStoreMiddleware(BaseHTTPMiddleware):
    """All API responses may contain patient data -> never cacheable."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for k, v in NO_STORE.items():
            response.headers[k] = v
        response.headers.setdefault("Vary", "Authorization, Origin")
        return response

def install_no_store(app: FastAPI) -> None:
    app.add_middleware(NoStoreMiddleware)
```

frontend/vercel.json (excerpt): index.html must not be cached; hashed assets may be.
```json
{
  "headers": [
    { "source": "/assets/(.*)", "headers": [{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }] },
    { "source": "/((?!assets/).*)", "headers": [{ "key": "Cache-Control", "value": "no-store, max-age=0" }] }
  ]
}
```

**Implementation Guidance:**
- Register `install_no_store(app)` in `backend/app/main.py` so every router (`backend/app/routers/*.py`) inherits it; do not rely on per-endpoint headers.
- Always include `no-store` (not only `no-cache`): `no-cache` alone still allows the browser to store the response.
- In `frontend/vercel.json`, mark `index.html` and SPA routes `no-store`; only content-hashed static assets under `/assets/` may be cached long-term since they contain no patient data.
- When serving reports from Supabase Storage, use short-lived signed URLs and set `cacheControl: "no-store"` (or `0`) on upload in `backend/app/services/reports.py`; never use public buckets for clinical reports.
- Web Cache Deception: the API must return 404 for unknown paths such as `/api/patients/123/style.css` (FastAPI does this by default; do not add catch-all routes), and Vercel must not have rewrite rules caching API paths.
- In the SPA (`frontend/src/services`), call `supabase.auth.signOut()` and clear React Query/in-memory caches on logout.
- Reference: SD Elements guidance for T64.

**Success Criteria:**
- [ ] Every API response (including 4xx/5xx) carries `Cache-Control` containing `no-store`, plus `Pragma: no-cache` and `Expires: 0`.
- [ ] `index.html` from the frontend deployment returns `Cache-Control: no-store`.
- [ ] `backend/tests/test_cache_headers.py` asserts the headers on `/api/patients`, `/api/alarms`, `/api/reports` and an error response.

**Status:** Pending
