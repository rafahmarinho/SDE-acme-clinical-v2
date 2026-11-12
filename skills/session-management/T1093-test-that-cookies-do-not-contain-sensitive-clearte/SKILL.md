---
name: t1093-test-that-cookies-do-not-contain-sensitive-clearte
description: Tests that browse ACME Clinical's sensitive screens and confirm no cookie carries patient data, roles, emails or JWTs in cleartext, and that tampering with cookies cannot change authorization.
---

# T1093: Test that cookies do not contain sensitive cleartext information

**Category:** CODE_FIX
**SD Elements:** [T1093](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1093/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
Functional tests would visit these screens and check content. They would not inspect cookies, so a role cookie, a last-patient cookie or a cookie-stored Supabase JWT would pass unnoticed.

**Secure Implementation Pattern:**
```typescript
// frontend/tests/e2e/cookie-content.spec.ts (Playwright)
const SENSITIVE_PAGES = ["/wards", "/patients", "/patients/1", "/monitoring", "/alarms",
                         "/devices", "/thresholds", "/reports", "/staff", "/profile"];
const FORBIDDEN = [/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\./, /@/, /nurse|physician|administrator|technician/i];

test("cookies contain no sensitive cleartext", async ({ page, context }) => {
  await loginAsDemo(page, "administrator");
  const patientNames = await fetchDemoPatientNames();          // from supabase/seed.sql
  for (const path of SENSITIVE_PAGES) {
    await page.goto(path);
    for (const c of await context.cookies()) {
      const value = decodeURIComponent(c.value);
      for (const re of FORBIDDEN) expect(value, `${c.name} on ${path}`).not.toMatch(re);
      for (const n of patientNames) expect(value).not.toContain(n);
      expect(c.name.startsWith("sb-")).toBe(false);             // no Supabase SSR token cookies
    }
  }
});
```
```python
# backend/tests/test_cookies.py
async def test_tampered_cookie_does_not_grant_role(api, nurse):
    r = await api.get("/staff", headers=nurse.auth_header, cookies={"role": "administrator"})
    assert r.status_code == 403
```

**Implementation Guidance:**
- Sensitive page list per SD Elements: ward view, patient list/detail, live monitoring, alarms, devices, threshold settings, reports, team management, profile.
- Implement `frontend/tests/e2e/cookie-content.spec.ts` (log in once per role) and the tamper test in `backend/tests/test_cookies.py`.
- If the optional `__Host-acme_rt` cookie exists, confirm it is an opaque Supabase refresh token (not a JWT) and that the server rejects a modified value (`POST /auth/refresh` returns `401`).
- Manual check: Chrome DevTools > Application > Cookies for the frontend and API origins on each sensitive page.
- Reference: SD Elements guidance for T1093.

**Success Criteria:**
- [ ] No cookie on any sensitive page contains PII, patient data, role names or JWTs.
- [ ] Tampered or forged cookies do not change authorization.
- [ ] Tests run in CI.

**Status:** Applied
