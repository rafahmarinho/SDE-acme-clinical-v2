---
name: t94-test-that-session-ids-are-not-leaked-through-urls
description: Tests confirming that ACME Clinical never places Supabase access/refresh tokens or session identifiers in URLs and that the FastAPI API refuses tokens supplied in the query string.
---

# T94: Test that session IDs are not leaked through URLs

**Category:** CODE_FIX
**SD Elements:** [T94](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T94/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Login and password recovery would be tested only for success. With Supabase's implicit flow the recovery redirect contains `#access_token=...`, and report/file download links are easy to build with `?token=`; no functional test would flag either.

**Secure Implementation Pattern:**
```python
# backend/tests/test_token_in_url.py
import pytest

@pytest.mark.parametrize("param", ["access_token", "token", "jwt"])
async def test_query_token_rejected(api, nurse, param):
    r = await api.get(f"/patients?{param}={nurse.access_token}")      # no Authorization header
    assert r.status_code in (400, 401)
    assert "patients" not in r.text.lower()

async def test_matrix_param_not_accepted(api, nurse):
    r = await api.get(f"/patients;session={nurse.session_id}")
    assert r.status_code in (401, 404)
```
```typescript
// frontend/tests/e2e/token-url.spec.ts (Playwright)
test("no token in any visited URL", async ({ page }) => {
  const urls: string[] = [];
  page.on("request", (r) => urls.push(r.url()));
  await loginAsDemo(page, "physician");
  await page.goto("/patients/1"); await page.goto("/reports"); await page.click("text=Download PDF");
  await completePasswordRecoveryFlow(page);
  for (const u of urls) expect(u).not.toMatch(/access_token=|refresh_token=|eyJ[A-Za-z0-9_-]{10,}\./);
  expect(page.url()).not.toMatch(/[?#&](code|access_token)=/);
});
```

**Implementation Guidance:**
- Backend tests in `backend/tests/test_token_in_url.py`; frontend Playwright test in `frontend/tests/e2e/token-url.spec.ts`, which collects every request URL (including the Realtime WebSocket URL, where only the public anon key is allowed) and fails on JWT-shaped strings.
- Manual check per SD Elements: copy the access token from DevTools, open a different browser, and request an authenticated API URL with the token appended as a parameter; the test fails if data is returned.
- Review Vercel runtime logs after the test run for any token-looking strings.
- Reference: SD Elements guidance for T94.

**Success Criteria:**
- [ ] No request URL or address-bar URL contains a user JWT or refresh token.
- [ ] Query-string tokens are rejected by the API.
- [ ] Vercel logs contain no tokens after the e2e run.

**Status:** Pending
