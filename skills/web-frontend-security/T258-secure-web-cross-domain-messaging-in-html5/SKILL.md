---
name: t258-secure-web-cross-domain-messaging-in-html5
description: Governs any postMessage use in the ACME Clinical SPA (e.g. an isolated 3D ward visualization iframe or pop-out live monitor): no message listeners unless needed, explicit target origins, exact origin matching, schema validation of message data and no DOM/eval sinks.
---

# T258: Secure web (cross domain) messaging in HTML5

**Category:** CODE_FIX
**SD Elements:** [T258](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T258/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
A 3D simulation view is a natural candidate for an iframe or separate window that exchanges bed/monitor state with the main app via `postMessage(data, "*")` and a listener that trusts any message. Any page could then inject fake vitals/alarms into the UI or receive patient data.

**Secure Implementation Pattern:**
```typescript
// frontend/src/lib/messaging.ts
import { z } from "zod";

const VIZ_ORIGIN = import.meta.env.VITE_VIZ_ORIGIN as string; // e.g. https://acme-viz.vercel.app

const VizMessage = z.discriminatedUnion("type", [
  z.object({ type: z.literal("bed-selected"), bedId: z.string().regex(/^[A-Z]\d{1,2}-\d{1,2}$/) }),
  z.object({ type: z.literal("ready") }),
]);
export type VizMessage = z.infer<typeof VizMessage>;

export function sendToViz(frame: HTMLIFrameElement, msg: unknown) {
  frame.contentWindow?.postMessage(msg, VIZ_ORIGIN); // never "*"
}

export function listenToViz(frame: HTMLIFrameElement, onMsg: (m: VizMessage) => void) {
  const handler = (e: MessageEvent) => {
    if (e.origin !== VIZ_ORIGIN) return;                 // exact match, no includes()
    if (e.source !== frame.contentWindow) return;        // only our frame
    const parsed = VizMessage.safeParse(e.data);
    if (!parsed.success) return;
    onMsg(parsed.data); // UI hint only; real actions go through the authenticated API
  };
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
}
```

**Implementation Guidance:**
- Default: do not add any `message` listener. Render the 3D view (Three.js/React Three Fiber) as a normal in-app component; only use an iframe if third-party/untrusted code must be isolated (T1543/T1544).
- If messaging is used, centralize it in `frontend/src/lib/messaging.ts`; ban direct `postMessage(..., "*")` and `addEventListener("message"` elsewhere (ESLint `no-restricted-syntax`).
- Validate `origin` by exact string equality against a configured origin, check `event.source`, and validate `data` with a zod schema.
- Never pass message data to `innerHTML`, `dangerouslySetInnerHTML`, `eval`, `new Function`, or URLs for navigation.
- Messages are not authorization: acknowledging alarms or binding monitors must still call FastAPI with the user's Bearer token, where role checks run.
- Send only minimal data (bed IDs, not patient names) to the visualization frame.
- Reference: SD Elements guidance for T258.

**Success Criteria:**
- [ ] No `postMessage(..., "*")` and no unmanaged `message` listeners in `frontend/src`.
- [ ] Origin check uses strict equality and payloads are schema-validated.
- [ ] Verified by T319 unit tests.

**Status:** Pending
