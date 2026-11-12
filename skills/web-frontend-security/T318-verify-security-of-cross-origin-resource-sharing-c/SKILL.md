---
name: t318-verify-security-of-cross-origin-resource-sharing-c
description: Implements and tests a strict CORS allow-list on the ACME Clinical FastAPI API (separate Vercel origin from the React SPA): exact-match origins, no wildcard, authentication on every verb, rejection of look-alike origins, and JSON-only endpoints that force a preflight.
---

# T318: Verify security of cross origin resource sharing (CORS)

**Category:** CODE_FIX
**SD Elements:** [T318](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T318/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel."
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
Because the SPA and API are on different origins, the quickest fix for browser CORS errors is `allow_origins=["*"]` or a regex such as `.*\.vercel\.app`, which lets any site (including any other Vercel project) call the clinical API from a victim's browser.

**Secure Implementation Pattern:**
```python
# backend/app/main.py
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings  # CORS_ALLOWED_ORIGINS="https://acme-clinical.vercel.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,  # exact list, never "*" or regex
    allow_credentials=False,                      # Bearer tokens, no cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)
```
```python
# backend/tests/test_cors.py
import pytest
BAD = ["https://evil.com", "https://acme-clinical.vercel.app.evil.com",
       "https://acme-clinicalxvercel.app", "http://acme-clinical.vercel.app",
       "https://notacme-clinical.vercel.app", "null"]

@pytest.mark.anyio
@pytest.mark.parametrize("origin", BAD)
async def test_untrusted_origin_rejected(client, origin, auth_headers):
    r = await client.options("/api/patients", headers={"Origin": origin,
        "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
    assert "access-control-allow-origin" not in r.headers
    r = await client.get("/api/patients", headers={"Origin": origin, **auth_headers})
    assert r.headers.get("access-control-allow-origin") is None

@pytest.mark.anyio
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
async def test_auth_required_any_verb(client, method):
    r = await client.request(method, "/api/patients", headers={"Origin": "https://acme-clinical.vercel.app"})
    assert r.status_code in (401, 405)
```

**Implementation Guidance:**
- Load `CORS_ALLOWED_ORIGINS` (comma-separated, exact origins) in `backend/app/core/config.py`; document it in `backend/.env.example`. Preview deployments get their own explicit value, not a wildcard.
- Never return `Access-Control-Allow-Origin: *` for the API; it is not public.
- Every router in `backend/app/routers/` depends on the auth dependency from `backend/app/core/security.py` regardless of method; `OPTIONS` preflight must not bypass auth for non-preflight requests.
- Accept only `application/json` bodies on state-changing routes (Pydantic models) so cross-origin writes always require a preflight (see T1541).
- Do not compute URLs/redirects from request input without validation.
- Manual: with HTTPie/curl, repeat the test matrix against the deployed API.
- Reference: SD Elements guidance for T318.

**Success Criteria:**
- [ ] `backend/tests/test_cors.py` passes: trusted origin gets ACAO echo; all look-alike origins get none.
- [ ] All verbs return 401 without a token, with and without `Origin`.
- [ ] No `*` or regex origin in config.

**Status:** Applied
