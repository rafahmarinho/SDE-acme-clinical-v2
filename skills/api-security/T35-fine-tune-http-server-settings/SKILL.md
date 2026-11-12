---
name: t35-fine-tune-http-server-settings
description: Fine-tune HTTP limits for the ACME Clinical API on Vercel (header count/size, URL length, body size, function duration and DB/statement timeouts) in application middleware and vercel.json, and notify administrators when limits are violated.
---

# T35: Fine-tune HTTP server settings

**Category:** CODE_FIX
**SD Elements:** [T35](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T35/)
**Priority:** 9/10 · **Phase:** requirements

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
On Vercel there is no Apache/Nginx config to tune, so developers assume the platform handles everything. The FastAPI function then accepts any header count, very long URLs and slow uploads up to the platform maximum, holds DB connections for the whole function lifetime, and nobody is told when abuse occurs.

**Secure Implementation Pattern:**
```python
# backend/app/core/middleware.py
MAX_HEADER_COUNT = 64
MAX_HEADER_BYTES = 16 * 1024
MAX_URL_BYTES = 2048

class RequestShapeMiddleware:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = scope["headers"]
            url_len = len(scope.get("raw_path", b"")) + len(scope.get("query_string", b""))
            if url_len > MAX_URL_BYTES:
                return await self._reject(scope, receive, send, 414, "uri_too_long")
            if len(headers) > MAX_HEADER_COUNT or sum(len(k) + len(v) for k, v in headers) > MAX_HEADER_BYTES:
                return await self._reject(scope, receive, send, 431, "headers_too_large")
        await self.app(scope, receive, send)

    async def _reject(self, scope, receive, send, status, code):
        sec_event("http_limit_violation", outcome="denied", code=code)
        await audit.notify_admins("http_limit_violation", {"code": code})   # rate-limited alert
        await _error("Request rejected", status)(scope, receive, send)
```
```json
// backend/vercel.json
{ "functions": { "api/index.py": { "maxDuration": 15, "memory": 512 } } }
```

**Implementation Guidance:**
- Enforce header count/size, URL length and body size (T536) in `backend/app/core/middleware.py`, registered outermost in `backend/app/main.py`.
- Timeouts: set `maxDuration` in `backend/vercel.json`; set DB `connect_timeout`, pool `timeout` and a `statement_timeout` (e.g. `set local statement_timeout = '5s'` in `backend/app/db.py` `transaction()`), and `idle_in_transaction_session_timeout` for the `acme_api` role in a migration.
- Concurrency: size the psycopg pool small per function instance (serverless fan-out multiplies connections) and use the Supabase pooler; limit Realtime channels per client.
- Notify administrators of violations through `notify_admins` in `backend/app/core/audit.py` (debounced by `ALERT_MIN_INTERVAL_SECONDS`) and security events in `backend/app/core/logging.py`.
- Platform-level connection/backlog/keep-alive tuning is owned by Vercel (see T374, INFRA).
- Reference: SD Elements guidance for T35.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_api_security.py`): 3 KB URL -> 414; 80 headers -> 431; both emit a `http_limit_violation` security event.
- [ ] `backend/vercel.json` defines `maxDuration`; DB statements exceeding `statement_timeout` fail with a generic 503/504.
- [ ] Admin notification is triggered (and rate-limited) on violations.

**Status:** Pending
