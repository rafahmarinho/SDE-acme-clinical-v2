---
name: t169-test-that-the-site-is-not-vulnerable-to-dom-based
description: Source-review and automated test recipe confirming that ACME Clinical React code never routes DOM sources (location, hash, query strings, referrer, Realtime payloads) into HTML/JS sinks without sanitization.
---

# T169: Test that the site is not vulnerable to DOM-based XSS

**Category:** CODE_FIX
**SD Elements:** [T169](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T169/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: "filters, loading states and error messages. Adapt navigation to user profiles")
> Source: specs/PRD.md, line 13

**What the spec implies (naive approach):**
Filters and search state are typically kept in the URL (`?ward=...&q=...`), Supabase password recovery returns tokens/errors in the URL hash, and error messages may be shown from `error_description` query params. Writing those values with `innerHTML` or using them in `href`/`window.location` is DOM-based XSS.

**Secure Implementation Pattern:**
```ts
// frontend/scripts/check-dom-sinks.ts (run in CI with tsx) - source inspection
import { readFileSync } from "node:fs";
import { globSync } from "glob";

const SINKS = /\.(innerHTML|outerHTML)\s*=|document\.write(ln)?\(|dangerouslySetInnerHTML|insertAdjacentHTML|\beval\(|new Function\(/;
const offenders = globSync("src/**/*.{ts,tsx}").filter((f) => SINKS.test(readFileSync(f, "utf8")));
if (offenders.length) { console.error("DOM sinks found:", offenders); process.exit(1); }
```
```tsx
// frontend/src/screens/__tests__/dom-xss.test.tsx
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { it, expect } from "vitest";
import { LoginScreen } from "../LoginScreen";

it("renders error_description from the URL as text", () => {
  const p = encodeURIComponent("<img src=x onerror=alert(1)>");
  const { container } = render(
    <MemoryRouter initialEntries={[`/login?error_description=${p}`]}><LoginScreen /></MemoryRouter>);
  expect(container.querySelector("img")).toBeNull();
});
```

**Implementation Guidance:**
- Inspect all JS/TS in `frontend/src` (source review is preferred over runtime testing): list sources (`location.*`, `document.URL`, `document.referrer`, `URLSearchParams`, hash fragments, `postMessage`, Supabase Realtime payloads, `localStorage`).
- List sinks (`innerHTML`, `outerHTML`, `document.write/writeln`, `insertAdjacentHTML`, `dangerouslySetInnerHTML`, `eval`, `href`/`src` assignments, `window.location = ...`).
- The test fails if any source reaches a sink without validation; render URL-derived values only via JSX text and validate redirect targets (see T11).
- Prefer showing fixed, mapped error messages over echoing `error_description`.
- Reference: SD Elements guidance for T169.

**Success Criteria:**
- [ ] `check-dom-sinks` CI step passes with zero offenders (or each one is reviewed and justified with sanitization).
- [ ] Vitest DOM-XSS tests for login, password reset and filtered list screens pass.

**Status:** Pending
