---
name: t95-test-for-the-absence-of-remember-me-features
description: Tests confirming ACME Clinical has no remember-me login, that the Supabase session does not outlive the browser session, and that critical actions require re-authentication.
---

# T95: Test for the absence of 'Remember Me' features

**Category:** CODE_FIX
**SD Elements:** [T95](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T95/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "devem aparecer nas telas e continuar salvos após recarregar a aplicação."
> (EN: must appear on the screens and remain saved after reloading the application.)
> Source: specs/PRD.md, line 45

**What the spec implies (naive approach):**
Tests derived from the PRD would check that data and the login survive a reload. They would not check that the login does *not* survive closing the browser, so the `supabase-js` default (`localStorage`) or an added remember-me checkbox would pass.

**Secure Implementation Pattern:**
```typescript
// frontend/tests/e2e/remember-me.spec.ts (Playwright)
test("login page has no remember-me control", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel(/remember|keep me signed in/i)).toHaveCount(0);
});

test("session survives reload but not a new browser session", async ({ browser }) => {
  const ctx = await browser.newContext(); const page = await ctx.newPage();
  await loginAsDemo(page, "nurse");
  await page.reload(); await expect(page.getByText("Ward overview")).toBeVisible();   // PRD: reload works
  expect(await page.evaluate(() => Object.keys(localStorage).some((k) => k.includes("auth-token")))).toBe(false);
  const state = await ctx.storageState();                 // what a "closed and reopened" browser keeps
  const reopened = await browser.newContext({ storageState: state });
  const p2 = await reopened.newPage(); await p2.goto("/patients");
  await expect(p2).toHaveURL(/\/login/);
});
```
```python
# backend/tests/test_reauth.py
async def test_password_change_requires_recent_auth(api, nurse, freeze_time):
    freeze_time.tick(minutes=10)
    r = await api.post("/profile/password", headers=nurse.auth_header, json={"new_password": "N3w-Strong-Pass!"})
    assert r.status_code == 401 and r.json()["error"] == "reauth_required"
```

**Implementation Guidance:**
- Playwright tests in `frontend/tests/e2e/remember-me.spec.ts`; `storageState` keeps cookies and `localStorage` but not `sessionStorage`, which models a browser restart.
- Backend tests in `backend/tests/test_reauth.py` for password, email, staff role and threshold changes.
- Manual check per SD Elements: log in on the deployed app, close all browser windows, reopen and browse to `/patients`; the test fails if the user is still logged in. Disable "Continue where you left off" during the test, since browser session restore can revive `sessionStorage`; mention in the README that ward workstations should have session restore disabled by policy.
- Reference: SD Elements guidance for T95.

**Success Criteria:**
- [ ] No remember-me control on the login page.
- [ ] Session does not survive a browser restart; it does survive a reload.
- [ ] Critical actions demand re-authentication.

**Status:** Pending
