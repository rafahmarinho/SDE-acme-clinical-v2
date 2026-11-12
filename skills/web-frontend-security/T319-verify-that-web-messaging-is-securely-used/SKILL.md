---
name: t319-verify-that-web-messaging-is-securely-used
description: Tests verifying that ACME Clinical either uses no web messaging at all or, if a 3D/visualization iframe exchanges postMessage data, uses explicit target origins, rejects look-alike origins, validates payloads and never grants privileged actions based on origin alone.
---

# T319: Verify that web messaging is securely used

**Category:** CODE_FIX
**SD Elements:** [T319](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T319/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "conseguir para simular as ações). Use pacientes fictícios e monitores simulados para mostrar"
> (EN: you manage to, to simulate the actions). Use fictitious patients and simulated monitors to show)
> Source: specs/PRD.md, line 29

**What the spec implies (naive approach):**
A 3D simulation view embedded in an iframe or separate window may use `postMessage`. Without tests, loose origin checks (`origin.includes("acme")`) or unvalidated data could let other pages inject fake vitals or trigger actions.

**Secure Implementation Pattern:**
```typescript
// frontend/src/lib/__tests__/messaging.test.ts
import { describe, it, expect, vi } from "vitest";
import { listenToViz, sendToViz } from "../messaging";

const ORIGIN = import.meta.env.VITE_VIZ_ORIGIN as string;
const frame = { contentWindow: { postMessage: vi.fn() } } as unknown as HTMLIFrameElement;
const fire = (origin: string, data: unknown) =>
  window.dispatchEvent(new MessageEvent("message", { origin, data, source: frame.contentWindow }));

describe("web messaging", () => {
  it.each([`${ORIGIN}.evil.com`, "https://evil.com?q=" + ORIGIN, ORIGIN.replace("https", "http"), "null"])(
    "rejects look-alike origin %s", (o) => {
      const cb = vi.fn(); const off = listenToViz(frame, cb);
      fire(o, { type: "ready" }); off();
      expect(cb).not.toHaveBeenCalled();
    });
  it("rejects malformed payloads", () => {
    const cb = vi.fn(); const off = listenToViz(frame, cb);
    fire(ORIGIN, { type: "bed-selected", bedId: "<img src=x onerror=alert(1)>" }); off();
    expect(cb).not.toHaveBeenCalled();
  });
  it("sends with explicit target origin", () => {
    sendToViz(frame, { type: "ready" });
    expect(frame.contentWindow!.postMessage).toHaveBeenCalledWith({ type: "ready" }, ORIGIN);
  });
});
```

**Implementation Guidance:**
- If the app uses no messaging, the test is a static check: `grep -rnE "postMessage|addEventListener\(\s*['\"]message" frontend/src` returns nothing outside `lib/messaging.ts` (wire into CI). This passes the SD Elements test.
- Otherwise add the vitest suite above (set `VITE_VIZ_ORIGIN` in `.env.test`); it verifies the control from T258.
- Review with developers that handlers never call the API for privileged operations solely because a message arrived; acknowledging alarms or binding monitors requires a user click and the Bearer-authenticated API.
- Confirm message data never reaches `innerHTML`/`eval` (ESLint `no-eval`, `react/no-danger`).
- Reference: SD Elements guidance for T319.

**Success Criteria:**
- [ ] Static grep check passes in CI, or the messaging vitest suite passes.
- [ ] Look-alike origins (`<origin>.evil.com`, `evil.com?q=<origin>`, `http://` variant) are rejected.

**Status:** Applied
