---
name: t119-test-for-clickjacking
description: Implements and tests anti-clickjacking protection for ACME Clinical so one-click clinical actions (acknowledge alarm, bind monitor to bed, reset simulation, change alarm limits) cannot be triggered from a hostile page that frames the SPA.
---

# T119: Test for clickjacking

**Category:** CODE_FIX
**SD Elements:** [T119](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T119/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
The SPA exposes single-click buttons with patient-safety impact (acknowledge alarm, unbind monitor, reset data). With Vercel defaults the page can be framed by any site, so an attacker could overlay invisible ACME Clinical buttons under a decoy and trick a logged-in nurse into acknowledging alarms.

**Secure Implementation Pattern:**
frontend/vercel.json (headers on every route):
```json
{ "headers": [{ "source": "/(.*)", "headers": [
  { "key": "X-Frame-Options", "value": "DENY" },
  { "key": "Content-Security-Policy", "value": "...; frame-ancestors 'none'; ..." }
] }] }
```
Type One automated test (frontend/tests/clickjacking.test.ts):
```typescript
import { it, expect } from "vitest";
import cfg from "../vercel.json";

it("all routes deny framing", () => {
  const rule = cfg.headers.find((h) => h.source === "/(.*)")!;
  const get = (k: string) => rule.headers.find((h) => h.key === k)?.value ?? "";
  expect(get("X-Frame-Options")).toBe("DENY");
  expect(get("Content-Security-Policy")).toMatch(/frame-ancestors 'none'/);
});
```
Type Two manual probe (host on an unrelated origin):
```html
<iframe src="https://acme-clinical.vercel.app/alarms" width="800" height="600"></iframe>
<iframe src="data:text/html,<iframe src='https://acme-clinical.vercel.app/alarms'></iframe>"></iframe>
```

**Implementation Guidance:**
- Set both `X-Frame-Options: DENY` (legacy browsers) and CSP `frame-ancestors 'none'` in `frontend/vercel.json`; the API sets `frame-ancestors 'none'` in `backend/app/core/security.py`.
- Do not rely on JavaScript frame-busting; if desired, add only as an extra layer in `frontend/src/main.tsx` (`if (window.top !== window.self) document.body.innerHTML = ""`).
- High-impact actions (reset simulation, unbind monitor, delete user) should also require a confirmation dialog, which reduces single-click exploitation.
- Tests: the vitest config test above (Type One) in CI; manual Type Two with the probe page (single and double framing) in each supported browser (Chrome, Edge, Firefox, Safari). The test fails if the SPA renders inside the iframe.
- Reference: SD Elements guidance for T119.

**Success Criteria:**
- [ ] Deployed responses on `/`, `/alarms`, `/patients/*`, `/simulation` include `X-Frame-Options: DENY` and `frame-ancestors 'none'`.
- [ ] Probe page shows a blocked frame (no ACME Clinical UI) in all supported browsers, including double framing.
- [ ] vitest clickjacking config test passes.

**Status:** Applied
