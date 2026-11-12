---
name: t111-test-that-your-application-turns-off-auto-complete
description: Frontend tests and a manual check verifying that ACME Clinical forms holding confidential data (patient search, identifiers, observations) disable browser autocomplete, and that the login form matches the documented password-manager decision.
---

# T111: Test that your application turns off auto-complete for confidential data fields

**Category:** CODE_FIX
**SD Elements:** [T111](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T111/)
**Priority:** 3/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Observation, search and patient forms are implemented in React; without a test, a new form or a refactor can reintroduce plain inputs and the browser starts suggesting patient names or notes typed by a previous user on a shared workstation.

**Secure Implementation Pattern:**
```tsx
// frontend/src/screens/__tests__/autocomplete.test.tsx
import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ObservationForm } from "../ObservationForm";
import { PatientSearch } from "../../components/PatientSearch";
import { LoginScreen } from "../LoginScreen";

const isOff = (el: Element) =>
  el.getAttribute("autocomplete") === "off" ||
  el.closest("form")?.getAttribute("autocomplete") === "off";

describe("confidential fields disable autocomplete", () => {
  it.each([["observation", ObservationForm], ["search", PatientSearch]])(
    "%s form", (_n, Comp) => {
      const { container } = render(<Comp />);
      const fields = container.querySelectorAll("input:not([type=hidden]), textarea");
      expect(fields.length).toBeGreaterThan(0);
      fields.forEach((f) => expect(isOff(f)).toBe(true));
    });

  it("login follows documented password-manager decision", () => {
    const { container } = render(<LoginScreen />);
    const pwd = container.querySelector("input[type=password]")!;
    expect(["current-password", "off"]).toContain(pwd.getAttribute("autocomplete"));
  });
});
```

**Implementation Guidance:**
- Add the vitest suite under `frontend/src/screens/__tests__/` (configure `environment: "jsdom"` in `vite.config.ts` test section); it verifies the control from T63.
- Cover every form that takes patient identifiers, observations, search terms, or user data in team management.
- Manual check on the deployed SPA: type a patient name in search, submit, reload, start typing again; the test fails if the browser suggests the previous value.
- Inspect elements in DevTools and confirm `autocomplete="off"` on the input or its parent `form`.
- Reference: SD Elements guidance for T111.

**Success Criteria:**
- [ ] `pnpm test` runs the autocomplete suite and it passes.
- [ ] Manual re-typing test on the deployed build shows no suggestions for patient search or observation fields.

**Status:** Applied
