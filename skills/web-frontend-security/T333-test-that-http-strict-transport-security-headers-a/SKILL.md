---
name: t333-test-that-http-strict-transport-security-headers-a
description: Tests verifying that the ACME Clinical SPA and FastAPI API Vercel deployments return a Strict-Transport-Security header with an adequate max-age on HTTPS responses and redirect HTTP to HTTPS.
---

# T333: Test that HTTP Strict-Transport-Security headers are sent in HTTPS responses

**Category:** CODE_FIX
**SD Elements:** [T333](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T333/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel."
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
With two separate deployments, HSTS could be present on one origin but missing on the other, or the policy could be too short. Without a test this is only discovered in an audit.

**Secure Implementation Pattern:**
```python
# backend/tests/test_hsts.py
import re
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.config import settings

@pytest.mark.anyio
async def test_hsts_present(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        r = await c.get("/api/health")
    hsts = r.headers.get("strict-transport-security", "")
    m = re.search(r"max-age=(\d+)", hsts)
    assert m and int(m.group(1)) >= 31536000
```
```bash
# post-deploy smoke check
for host in "$WEB_HOST" "$API_HOST"; do
  curl -sI "https://$host/" | grep -Ei '^strict-transport-security: max-age=[0-9]{8,}' || echo "FAIL $host"
  curl -sI "http://$host/" | grep -Ei '^(HTTP/1.1 30[18]|location: https://)' || echo "FAIL redirect $host"
done
```

**Implementation Guidance:**
- Add `backend/tests/test_hsts.py`; it verifies the middleware from T322 (the middleware must read `settings.environment` at request time for the monkeypatch to apply).
- Add the curl smoke check to the README deploy section / CI after Vercel deploys for both the web and API hosts.
- Manual: in Chrome DevTools > Network, load the app over HTTPS and inspect the document and an API XHR response for `Strict-Transport-Security`.
- The test fails if the header is missing on either origin or `max-age` is below policy (1 year).
- Reference: SD Elements guidance for T333.

**Success Criteria:**
- [ ] pytest HSTS test passes.
- [ ] Smoke check passes for both Vercel hosts (HSTS present, HTTP redirects to HTTPS).

**Status:** Pending
