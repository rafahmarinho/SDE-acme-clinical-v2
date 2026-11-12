---
name: t1540-verify-that-browser-data-is-cleared-upon-user-logo
description: Ensure and test that logging out of ACME Clinical on a shared ward workstation removes tokens and patient data from every browser storage area of the SPA origin, using the Clear-Site-Data header served from the frontend origin plus explicit client-side clearing.
---

# T1540: Verify that browser data is cleared upon user logout

**Category:** CODE_FIX
**SD Elements:** [T1540](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1540/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
The SPA caches patient lists, vitals and observations (query cache, `sessionStorage`, possibly IndexedDB or the HTTP cache) and `supabase-js` stores the session under `sb-<project-ref>-auth-token`. A plain `signOut()` removes only that key. Adding `Clear-Site-Data` to the FastAPI logout response is also not enough on its own: the header only clears data for the origin that served the response, and the API is a different Vercel deployment than the SPA.

**Secure Implementation Pattern:**
frontend/vercel.json (static page on the SPA origin that triggers the clearing):
```json
{
  "headers": [
    {
      "source": "/signed-out",
      "headers": [
        { "key": "Clear-Site-Data", "value": "\"cache\", \"cookies\", \"storage\"" },
        { "key": "Cache-Control", "value": "no-store" }
      ]
    }
  ]
}
```
```typescript
// frontend/src/services/auth.ts (end of logout(), see T26)
await supabase.auth.signOut({ scope: "local" });
queryClient.clear();
sessionStorage.clear();
Object.keys(localStorage).filter((k) => k !== "acme.lastEmail").forEach((k) => localStorage.removeItem(k));
indexedDB.databases?.().then((dbs) => dbs.forEach((d) => d.name && indexedDB.deleteDatabase(d.name)));
if ("caches" in window) (await caches.keys()).forEach((k) => caches.delete(k));
window.location.replace("/signed-out");   // full navigation so the header is applied to the SPA origin
```

**Implementation Guidance:**
- Serve `/signed-out` as a real path on the frontend Vercel project (add it before the SPA catch-all rewrite, or ship `public/signed-out.html`) so the `Clear-Site-Data` header comes from the SPA origin. If the API is proxied under `/api` on the same origin (T557), also return the header from `POST /api/auth/logout`.
- Keep the explicit client-side clearing for browsers that do not support the header.
- The FastAPI logout (`backend/app/routers/auth.py`) still returns `Clear-Site-Data` for the API origin and revokes the session server-side (T26).
- Automated test (`frontend/tests/e2e/logout-storage.spec.ts`, Playwright Chromium): log in as the demo physician, open several patients and live monitoring, log out, then assert: `document.cookie === ""`, `localStorage` has no keys except an optional `acme.lastEmail`, `sessionStorage.length === 0`, `indexedDB.databases()` is empty, `caches.keys()` is empty, and the response for `/signed-out` carried the header.
- Manual check per SD Elements: in a supporting browser, inspect DevTools > Application before and after logout (Cookies, Local Storage, Session Storage, IndexedDB, Cache Storage). The test fails if any token or patient data remains.
- Reference: SD Elements guidance for T1540.

**Success Criteria:**
- [ ] `/signed-out` response includes `Clear-Site-Data: "cache", "cookies", "storage"`.
- [ ] After logout no auth token, patient name, vital value or observation is present in any storage area of the SPA origin.
- [ ] The e2e test runs in CI on Chromium.

**Status:** Pending
