---
name: t513-verify-that-access-to-the-opener-is-restricted-in
description: Tests verifying that links and windows opened from the ACME Clinical SPA (reports, stored files, external device links) cannot access or redirect the opener tab, covering static links, user-supplied links and window.open calls.
---

# T513: Verify that access to the opener is restricted in opened window

**Category:** CODE_FIX
**SD Elements:** [T513](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T513/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Reports, file downloads and possibly external links open in new tabs. Without a test, a new screen can add a `target="_blank"` link or `window.open` call that leaves `window.opener` accessible, enabling reverse tabnabbing of the clinician's authenticated session.

**Secure Implementation Pattern:**
```tsx
// frontend/src/lib/__tests__/opener.test.tsx
import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ExternalLink } from "../../components/ExternalLink";
import { openSafely } from "../openWindow";

describe("opener isolation", () => {
  it("ExternalLink always sets noopener noreferrer", () => {
    const { getByRole } = render(<ExternalLink href="https://example.org">x</ExternalLink>);
    const rel = getByRole("link").getAttribute("rel") ?? "";
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");
  });

  it("openSafely passes noopener and nulls opener", () => {
    const fake = { opener: {} } as unknown as Window;
    const spy = vi.spyOn(window, "open").mockReturnValue(fake);
    openSafely("https://files.example.org/report.pdf");
    expect(spy.mock.calls[0][2]).toContain("noopener");
    expect(fake.opener).toBeNull();
  });
});
```

```html
<!-- manual probe page B.html, hosted on a test origin -->
<script>
  if (window.opener) { opener.location = "https://example.org/pwned"; }
  else { document.write("Safe Use!"); }
</script>
```

**Implementation Guidance:**
- Inventory all external links, user-supplied links (maintenance notes) and `window.open` calls: `grep -rn "target=\"_blank\"\|window.open" frontend/src`.
- Add the vitest suite above; it verifies the control from T512. Keep ESLint `react/jsx-no-target-blank` as a static gate.
- Manual test: temporarily point a link (or post a maintenance note link) to `B.html`; click it from the SPA. The test fails if the original ACME Clinical tab is redirected.
- In DevTools, inspect rendered links and confirm `rel` contains `noopener`.
- Reference: SD Elements guidance for T513.

**Success Criteria:**
- [ ] vitest opener suite passes in CI.
- [ ] Manual B.html probe shows "Safe Use!" and the opener tab is not redirected in Chrome, Firefox and Safari.

**Status:** Pending
