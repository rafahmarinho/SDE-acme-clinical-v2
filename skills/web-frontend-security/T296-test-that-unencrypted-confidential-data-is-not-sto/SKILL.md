---
name: t296-test-that-unencrypted-confidential-data-is-not-sto
description: Tests that the ACME Clinical SPA stores nothing confidential in browser storage beyond the Supabase Auth session (no patient data, observations or search terms in localStorage/sessionStorage/IndexedDB/Cache Storage) and that the Vercel deployments and Supabase Storage expose no secrets or unprotected patient files.
---

# T296: Test that unencrypted confidential data is not stored without access control mechanisms

**Category:** CODE_FIX
**SD Elements:** [T296](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T296/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "devem aparecer nas telas e continuar salvos após recarregar a aplicação."
> (EN: must appear on the screens and remain saved after reloading the application.)
> Source: specs/PRD.md, line 45

**What the spec implies (naive approach):**
"Remain saved after reloading" can be misread as "persist in the browser": a developer may cache patient lists, vitals, observations or React Query state in `localStorage` to survive reloads. On shared ward workstations that data stays unencrypted on disk after logout. Persistence must come from Supabase PostgreSQL, not the browser.

**Secure Implementation Pattern:**
```typescript
// frontend/tests/e2e/storage.spec.ts (Playwright)
import { test, expect } from "@playwright/test";

const PHI = [/demo patient/i, /\bMRN[-\s]?\d+/i, /observation/i, /"spo2"/i, /"heart_rate"/i];

test("browser storage holds only the Supabase session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.E2E_NURSE_EMAIL!);
  await page.getByLabel("Password").fill(process.env.E2E_NURSE_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.goto("/patients"); await page.getByRole("link").first().click();

  const dump = await page.evaluate(async () => ({
    local: Object.entries(localStorage), session: Object.entries(sessionStorage),
    idb: (await indexedDB.databases()).map((d) => d.name), caches: await caches.keys(),
  }));
  const keys = dump.local.map(([k]) => k);
  expect(keys.every((k) => /^sb-[a-z0-9]+-auth-token$/.test(k) || k === "acme-ui-prefs")).toBe(true);
  const blob = JSON.stringify(dump.local.filter(([k]) => !k.startsWith("sb-")).concat(dump.session));
  PHI.forEach((re) => expect(blob).not.toMatch(re));
  expect(dump.caches).toHaveLength(0);

  await page.getByRole("button", { name: "Sign out" }).click();
  expect(await page.evaluate(() => localStorage.length)).toBeLessThanOrEqual(1); // ui prefs only
});
```

**Implementation Guidance:**
- Add the Playwright spec under `frontend/tests/e2e/`; run against a Preview deployment with demo users. It verifies: only the Supabase session (`sb-<ref>-auth-token`) and non-sensitive UI prefs are stored; no PHI in storage; cleared on sign-out.
- Do not use React Query persisters, service-worker caches or IndexedDB for clinical data; data persistence after reload comes from Supabase.
- Server side: confirm no secrets in the frontend bundle (`grep -r "service_role\|SUPABASE_SERVICE" frontend/dist` must be empty; only `VITE_SUPABASE_ANON_KEY` is public). Backend secrets live only in Vercel env vars, not in repo files besides `.env.example` placeholders.
- Supabase Storage: confirm the reports/attachments buckets are private (anonymous `GET /storage/v1/object/public/...` returns 400/404) and RLS on `storage.objects` restricts by role.
- Supabase session in localStorage is an accepted risk of supabase-js; mitigate with short JWT expiry, sign-out on idle, and CSP (T331).
- Reference: SD Elements guidance for T296.

**Success Criteria:**
- [ ] Playwright storage spec passes; after sign-out no session or PHI remains.
- [ ] Bundle secret scan finds no service-role key; buckets are private.

**Status:** Applied
