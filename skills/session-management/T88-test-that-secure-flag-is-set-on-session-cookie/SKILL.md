---
name: t88-test-that-secure-flag-is-set-on-session-cookie
description: Tests verifying that every session or refresh cookie set by ACME Clinical carries the Secure attribute and __Host- prefix, plus a manual browser check on the deployed Vercel apps.
---

# T88: Test that secure flag is set on session cookie

**Category:** CODE_FIX
**SD Elements:** [T88](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T88/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
A team would only check that the Vercel URLs open over HTTPS. Nobody would check the attributes on the cookies; a missing `Secure` flag on an optional refresh cookie (T22/T23) would ship unnoticed. With the default Bearer-token design the test mostly proves that no session cookie is set at all.

**Secure Implementation Pattern:**
```python
# backend/tests/test_cookies.py
import re

async def test_session_cookies_are_secure(api, demo_credentials, nurse):
    responses = [
        await api.post("/auth/login", json=demo_credentials("nurse")),   # optional BFF login
        await api.post("/auth/refresh"),
        await api.post("/auth/logout", headers=nurse.auth_header),
    ]
    for r in responses:
        for c in r.headers.get_list("set-cookie"):
            attrs = [a.strip().lower() for a in c.split(";")]
            assert "secure" in attrs, c
            if c.startswith("__Host-"):
                assert "path=/" in attrs and not any(a.startswith("domain=") for a in attrs)

async def test_hsts_present(api):
    r = await api.get("/health")
    assert re.search(r"max-age=\d{7,}", r.headers["strict-transport-security"])
```

**Implementation Guidance:**
- Add the tests to `backend/tests/test_cookies.py`; skip the `/auth/login` case if the BFF cookie option is not implemented, but keep the generic `Set-Cookie` scan.
- Manual check per SD Elements: log in on the deployed frontend, inspect cookies in DevTools for the frontend and API origins; any session/refresh cookie must show "Secure". Record that the Supabase session itself lives in `sessionStorage`, not a cookie.
- Reference: SD Elements guidance for T88.

**Success Criteria:**
- [ ] No session/refresh cookie without `Secure` in any API response.
- [ ] `__Host-` cookies have `Path=/` and no `Domain`.
- [ ] HSTS test passes in CI.

**Status:** Applied
