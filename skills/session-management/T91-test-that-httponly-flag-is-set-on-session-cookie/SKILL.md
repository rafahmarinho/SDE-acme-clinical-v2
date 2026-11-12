---
name: t91-test-that-httponly-flag-is-set-on-session-cookie
description: Tests that confirm ACME Clinical stores no auth tokens in JavaScript-readable cookies and that any session or refresh cookie set by the FastAPI API carries the HttpOnly flag.
---

# T91: Test that HttpOnly flag is set on session cookie

**Category:** CODE_FIX
**SD Elements:** [T91](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T91/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Login would be tested functionally only. With Bearer tokens in Web Storage there is usually no session cookie at all, so the test must assert two things: (1) no auth token leaks into a non-HttpOnly cookie (for example via `@supabase/ssr` cookie storage), and (2) if the optional FastAPI refresh cookie exists, it is HttpOnly.

**Secure Implementation Pattern:**
```python
# backend/tests/test_cookies.py
SESSION_COOKIE_NAMES = ("__Host-acme_rt",)

def _set_cookie_headers(resp):
    return resp.headers.get_list("set-cookie")

async def test_refresh_cookie_is_httponly(api, demo_credentials):
    r = await api.post("/auth/login", json=demo_credentials("nurse"))
    cookies = [c for c in _set_cookie_headers(r) if c.startswith(SESSION_COOKIE_NAMES)]
    for c in cookies:                       # empty list is fine when no cookie is used
        assert "httponly" in c.lower()

async def test_no_endpoint_sets_readable_auth_cookie(api, nurse):
    for path in ("/auth/session", "/profile", "/patients"):
        r = await api.request("POST" if path == "/auth/session" else "GET", path, headers=nurse.auth_header)
        for c in _set_cookie_headers(r):
            name = c.split("=", 1)[0]
            assert not name.startswith("sb-"), f"Supabase token cookie set by API: {name}"
            assert "httponly" in c.lower(), f"cookie {name} readable by JavaScript"
```
```typescript
// frontend/tests/e2e/cookies.spec.ts (Playwright)
test("no JS-readable auth cookie after login", async ({ page, context }) => {
  await loginAsDemo(page, "nurse");
  expect(await page.evaluate(() => document.cookie)).not.toMatch(/sb-.*-auth-token|acme_rt/);
  for (const c of await context.cookies()) if (/acme_rt/.test(c.name)) expect(c.httpOnly).toBe(true);
});
```

**Implementation Guidance:**
- Add `backend/tests/test_cookies.py` and `frontend/tests/e2e/cookies.spec.ts` as above.
- Manual check per SD Elements: log in on the deployed Vercel frontend, open DevTools > Application > Cookies for both the frontend and API origins, and confirm any session/refresh cookie shows the HttpOnly tick. Ignore Vercel platform cookies (for example deployment-protection cookies) but note them in the report.
- Reference: SD Elements guidance for T91.

**Success Criteria:**
- [ ] `document.cookie` after login contains no auth token.
- [ ] Every session/refresh cookie in `Set-Cookie` responses contains `HttpOnly`.
- [ ] Both tests run in CI.

**Status:** Applied
