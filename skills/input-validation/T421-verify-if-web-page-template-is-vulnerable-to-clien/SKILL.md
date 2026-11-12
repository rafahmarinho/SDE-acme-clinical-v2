---
name: t421-verify-if-web-page-template-is-vulnerable-to-clien
description: Test recipe injecting template and expression payloads into ACME Clinical user-authored fields (observations, names, notes, search) and verifying the React frontend renders them as inert text.
---

# T421: Verify if web page template is vulnerable to client side template injection (CSTI)

**Category:** CODE_FIX
**SD Elements:** [T421](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T421/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow linking a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
User text is displayed back on several screens. Any later addition of a template helper, markdown renderer or `eval` could turn stored observations into executed expressions; a test is needed to catch regressions.

**Secure Implementation Pattern:**
```tsx
// frontend/src/components/__tests__/csti.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ObservationItem } from "../ObservationItem";

const PAYLOADS = [
  "{{7*7}}", "${7*7}", "{{constructor.constructor('alert(1)')()}}",
  "<img src=x onerror=alert(1)>", "#{7*7}",
];

describe("CSTI", () => {
  it.each(PAYLOADS)("renders %s literally", (p) => {
    const alert = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { container } = render(<ObservationItem author="Nurse" text={p} createdAt="2026-01-01T00:00:00Z" />);
    expect(screen.getByText(p)).toBeTruthy();
    expect(container.textContent).not.toContain("49");
    expect(container.querySelector("img")).toBeNull();
    expect(alert).not.toHaveBeenCalled();
  });
});
```

**Implementation Guidance:**
- Identify every component rendering user-controlled data (observations, alarm notes, staff names, maintenance notes, search echo, profile name).
- Inject expression payloads for common template syntaxes (`{{ }}`, `${ }`, `#{ }`) and sandbox-escape payloads; verify output shows the literal string and nothing evaluates.
- Statically review `frontend/src` for `eval`, `new Function`, `dangerouslySetInnerHTML`, template compile calls; any user data flowing into them fails the test.
- Manual E2E: save an observation with `{{7*7}}` via the API and view it on patient detail and ward screens.
- Reference: SD Elements guidance for T421.

**Success Criteria:**
- [ ] Vitest CSTI suite passes for all user-content components.
- [ ] Manual check documented: stored payloads display literally on every screen.

**Status:** Pending
