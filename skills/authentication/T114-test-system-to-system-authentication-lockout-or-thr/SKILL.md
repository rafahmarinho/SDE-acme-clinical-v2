---
name: t114-test-system-to-system-authentication-lockout-or-thr
description: Test that ACME Clinical's machine-to-machine entry points (Vercel Cron and internal simulation endpoints protected by a shared secret, and service JWT verification) throttle or lock out callers after repeated invalid credentials.
---

# T114: Test system-to-system authentication lockout or throttling

**Category:** CODE_FIX
**SD Elements:** [T114](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T114/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "Inclua uma área para escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados."
> (EN: Include an area to choose scenarios, advance the simulation, view events and reset the data.)
> Source: specs/PRD.md, lines 41-43

**What the spec implies (naive approach):**
Advancing the simulation and generating readings would likely run from a Vercel Cron job or an internal endpoint guarded by a static secret. Without throttling, an attacker can guess the secret without limit, then reset the demo data or inject readings.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py - guard for /internal/* (pattern under test)
import hmac
from fastapi import Header, HTTPException, Request

async def require_internal_secret(request: Request, authorization: str = Header("")):
    ip = request.headers.get("x-forwarded-for", "?").split(",")[0].strip()
    if await limiter.is_blocked(f"internal:{ip}"):            # e.g. Upstash Redis / Postgres counter
        raise HTTPException(429, "Too many attempts", headers={"Retry-After": "300"})
    expected = f"Bearer {settings.internal_cron_secret.get_secret_value()}"
    if not hmac.compare_digest(authorization.encode(), expected.encode()):
        await limiter.hit(f"internal:{ip}", limit=5, window_s=300)
        raise HTTPException(401, "Authentication failed")
```
```python
# backend/tests/test_internal_throttling.py
async def test_internal_auth_throttles_after_five_failures(client, settings):
    for _ in range(5):
        r = await client.post("/internal/simulation/tick", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401
    good = {"Authorization": f"Bearer {settings.internal_cron_secret.get_secret_value()}"}
    r = await client.post("/internal/simulation/tick", headers=good)
    assert r.status_code == 429                        # 6th try blocked even with valid secret
    assert "Retry-After" in r.headers
```

**Implementation Guidance:**
- Identify the system accounts: the Vercel Cron caller (`CRON_SECRET` bearer on `/internal/*`), the backend's service role key used toward Supabase, and any simulated device credentials (T425).
- Test steps 1 to 3: send 5 invalid secrets, then the valid one. The test fails if the 6th attempt succeeds immediately.
- The rate-limit store must be shared across Vercel serverless instances (Postgres table or Upstash Redis). An in-memory dictionary does not survive between invocations. Use the Vercel-provided client IP header.
- Inbound calls to Supabase with a bad service key are rejected and rate-limited by the platform. Record this as platform behavior rather than an app test.
- Reference: SD Elements guidance for T114.

**Success Criteria:**
- [ ] The pytest test passes: 429 on the 6th attempt, with `Retry-After`.
- [ ] Throttling state is shared across instances (an integration test with two app instances, or the limiter backed by Postgres or Redis).

**Status:** Applied
