---
name: t1362-perform-message-throttling-in-web-apis
description: Throttle ACME Clinical API traffic per client IP, per authenticated user and per sensitive route (login-adjacent endpoints, password recovery, simulation advance/reset, report exports, uploads) with 429 + Retry-After, plus server-side bounds on result sizes and work per request.
---

# T1362: Perform message throttling in Web APIs

**Category:** CODE_FIX
**SD Elements:** [T1362](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1362/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: choose scenarios, advance the simulation, view events and reset the data. The results)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
The API is public on Vercel and exposes costly operations (advance/reset simulation, report generation and CSV export, file uploads, staff invitations that send email). Without throttling, a script can loop `POST /simulation/reset`, scrape all patients page by page, or trigger thousands of invitation/recovery emails, exhausting database connections and Supabase quotas.

**Secure Implementation Pattern:**
```python
# backend/app/core/middleware.py
@dataclass(frozen=True)
class RouteLimit:
    method: str; pattern: re.Pattern; per_minute: int; key: str   # key: "ip" | "user"

ROUTE_LIMITS = (
    RouteLimit("POST", re.compile(r"^/simulation/(reset|advance)$"), 6, "user"),
    RouteLimit("GET",  re.compile(r"^/reports/export\.csv$"), 5, "user"),
    RouteLimit("POST", re.compile(r"^/files/patients/[^/]+$"), 10, "user"),
    RouteLimit("POST", re.compile(r"^/staff$"), 10, "user"),
)
GLOBAL_PER_IP_PER_MINUTE = 300

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        for rule in self._matching(request):
            key = f"{rule.pattern.pattern}:{self._subject(request, rule.key)}"
            allowed, retry_after = await self.store.hit(key, limit=rule.per_minute, window=60)
            if not allowed:
                sec_event("rate_limited", outcome="denied", route=request.url.path)
                return JSONResponse({"error": {"code": "rate_limited", "message": "Too many requests"}},
                                    status_code=429, headers={"Retry-After": str(retry_after)})
        return await call_next(request)
```

**Implementation Guidance:**
- Implement/extend `RateLimitMiddleware` and `RouteLimit` in `backend/app/core/middleware.py`: a global per-IP limit plus stricter per-user limits on expensive routes in `backend/app/routers/{simulation,reports,files,staff,profile}.py`.
- Vercel functions are stateless and multi-instance: use a shared store (a Postgres `rate_limit_buckets` table with `insert ... on conflict` in a migration, or Upstash/Vercel KV) rather than process memory for limits that must hold.
- Derive the client IP from the platform header (`x-vercel-forwarded-for`) via `client_ip()`; never trust arbitrary `X-Forwarded-For` chains.
- Login, password recovery and OTP are handled by Supabase Auth: configure `[auth.rate_limit]` in `supabase/config.toml` (e.g. `email_sent`, `sign_in_sign_ups`, `token_verifications`) and keep CAPTCHA option documented (T2).
- Bound work per request: `MAX_PAGE_SIZE`/`MAX_OFFSET` in `backend/app/schemas/__init__.py`, simulation `steps` max, report date range max, upload size max (T536).
- Return 429 with `Retry-After`, log a `rate_limited` security event, and alert admins on sustained abuse (`notify_admins` in `backend/app/core/audit.py`).
- Configure spending limits / usage alerts in Vercel and Supabase (documented in `docs/security/deployment.md`).
- Reference: SD Elements guidance for T1362.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_api_security.py`): the 7th `POST /simulation/reset` within a minute by the same user returns 429 with `Retry-After`.
- [ ] Limits are enforced across instances (shared store) and per user, not only per IP.
- [ ] `supabase/config.toml` sets explicit `[auth.rate_limit]` values.

**Status:** Pending
