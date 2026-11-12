---
name: t1363-verify-if-message-throttling-is-properly-performed
description: Implement and test rate limiting for the ACME Clinical FastAPI API on Vercel (per user and per IP, backed by shared storage, plus Vercel Firewall and Supabase Auth limits), using a script that sends requests every n milliseconds and expects HTTP 429 with Retry-After.
---

# T1363: Verify if message throttling is properly performed in Web APIs

**Category:** CODE_FIX
**SD Elements:** [T1363](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1363/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados."
> (EN: choose scenarios, advance the simulation, view events and reset the data.)
> Source: specs/PRD.md, line 43

> "Use Python com FastAPI e Pydantic no backend e"
> (EN: Use Python with FastAPI and Pydantic on the backend and)
> Source: specs/PRD.md, line 17

**What the spec implies (naive approach):**
Endpoints like `POST /simulation/advance`, `POST /simulation/reset` and report generation are expensive Python work. Without throttling, a script can loop them, exhausting Vercel function time and Supabase connections. An in-memory limiter (default `slowapi` storage) looks fine locally but is ineffective on Vercel, where each request may hit a different serverless instance.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py - shared-store limiter (Upstash Redis via REST, or a Postgres table)
from slowapi import Limiter
from slowapi.util import get_remote_address

def rate_key(request: Request) -> str:
    sub = getattr(request.state, "user_id", None)              # set by auth dependency
    return f"user:{sub}" if sub else f"ip:{request.headers.get('x-real-ip', get_remote_address(request))}"

limiter = Limiter(key_func=rate_key, storage_uri=settings.rate_limit_storage_uri,  # e.g. redis(s)://...
                  default_limits=["120/minute"], headers_enabled=True)

# backend/app/routers/simulation.py
@router.post("/simulation/reset", status_code=202)
@limiter.limit("3/minute")
async def reset(request: Request, sess=Depends(require_role("administrator"))): ...

# backend/tests/manual/throttle_probe.py - SD Elements probe: IP / token / interval n
async def probe(url: str, token: str | None, n_ms: int, count: int = 300, ip: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if ip: headers["X-Forwarded-For"] = ip                   # must NOT change the bucket
    async with httpx.AsyncClient() as c:
        codes = []
        for _ in range(count):
            codes.append((await c.get(url, headers=headers)).status_code); await asyncio.sleep(n_ms / 1000)
    print({code: codes.count(code) for code in set(codes)})
```

**Implementation Guidance:**
- Limits (document in `backend/app/core/config.py`): default 120 req/min per user; reads used by live views (vitals, alarms) sized to the UI polling rate; `POST /simulation/*` 10/min, `/simulation/reset` 3/min, report generation 5/min; unauthenticated requests 30/min per IP.
- Use shared storage (Upstash Redis or a Supabase `rate_limits` table with an atomic upsert) so limits hold across Vercel instances. Add a Vercel Firewall rate-limit rule on the API project as an outer layer.
- Derive the client IP from Vercel's `x-real-ip`/the first trusted hop, never from a client-supplied `X-Forwarded-For` value.
- Login and password recovery go directly to Supabase Auth; review its rate limits (sign-in, recovery email) in the Supabase dashboard.
- Return `429` with `Retry-After` and a generic JSON body; the SPA shows "Too many requests, please wait".
- Tests: `backend/tests/test_rate_limit.py` (pytest with a local Redis/fake store) sends limit+1 requests and asserts `429`; run `throttle_probe.py` against a staging deployment with varying `n`, token and spoofed IP header, and record results.
- Reference: SD Elements guidance for T1363.

**Success Criteria:**
- [ ] Exceeding a limit returns `429` with `Retry-After`; requests below the limit succeed.
- [ ] Limits apply per user across Vercel instances (staging probe confirms).
- [ ] Spoofed `X-Forwarded-For` does not reset the bucket.
- [ ] Rate-limit tests run in CI.

**Status:** Pending
