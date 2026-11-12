---
name: t436-verify-web-browsers-do-not-enable-mime-sniffing
description: Tests verifying that the ACME Clinical FastAPI API and the React SPA on Vercel return X-Content-Type-Options nosniff on every response, including errors and static assets.
---

# T436: Verify web browsers do not enable MIME sniffing

**Category:** CODE_FIX
**SD Elements:** [T436](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T436/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel."
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
Two separate Vercel deployments each need their own header configuration. A developer might configure one and forget the other, or headers may be lost on error responses or static files.

**Secure Implementation Pattern:**
```python
# backend/tests/test_security_headers.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/api/health", "/api/patients", "/does-not-exist"])
async def test_nosniff_on_all_responses(path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        r = await c.get(path)
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("content-type", "").split(";")[0] in {"application/json", "text/plain"}
```

```bash
# scripts/check-headers.sh (manual/CI smoke test against deployments)
for url in "$WEB_URL/" "$WEB_URL/assets/index.js" "$API_URL/api/health"; do
  curl -sI "$url" | grep -qi '^x-content-type-options: nosniff' || { echo "FAIL $url"; exit 1; }
done
```

**Implementation Guidance:**
- Add the pytest above under `backend/tests/`; it verifies the middleware from T435, including 404s.
- Add a post-deploy smoke check (documented in README or a CI job) that curls the frontend root, a hashed asset and an API endpoint; use the real asset name from the build.
- Also review `frontend/vercel.json` to confirm the header rule uses `"source": "/(.*)"`.
- Reference: SD Elements guidance for T436.

**Success Criteria:**
- [ ] pytest header suite passes.
- [ ] Smoke check reports `nosniff` on frontend HTML, JS assets and API responses after each deploy.

**Status:** Applied
