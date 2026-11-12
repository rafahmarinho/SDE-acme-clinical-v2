---
name: t752-verify-if-users-are-notified-about-processing-thei
description: Test recipe confirming ACME Clinical's privacy notice is linked from every page, shown just in time on data-collection forms, contains required processing details, and is re-presented when updated.
---

# T752: Verify if users are notified about processing their personal information

**Category:** CODE_FIX
**SD Elements:** [T752](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T752/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Without explicit requirements the privacy notice is either missing or only on one page, lacks recipients/retention, and is never re-shown when it changes. There is no evidence that users were notified.

**Secure Implementation Pattern:**
```typescript
// frontend/src/screens/__tests__/privacyNotice.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "../../App";

const routes = ["/login", "/forgot-password", "/wards", "/patients", "/profile", "/settings"];

it.each(routes)("shows privacy notice link on %s", (path) => {
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  expect(screen.getByRole("link", { name: /privacy notice/i })).toBeInTheDocument();
});

it("privacy page lists purposes, categories, recipients and retention", () => {
  render(<MemoryRouter initialEntries={["/privacy"]}><App /></MemoryRouter>);
  for (const h of [/purpose/i, /categories/i, /recipients/i, /retention/i]) {
    expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
  }
});
```

**Implementation Guidance:**
- Verify the controls from T751: footer link on all routes (`frontend/src/components/`), `/privacy` page content, just-in-time notes on forms.
- Backend test (`backend/tests/test_consent.py`): bump `PRIVACY_NOTICE_VERSION`; `GET /me` returns `notice_required: true` for users who accepted an older version.
- Evidence: keep notice versions in git history and `consents` table entries with timestamps.
- Test fails if any route lacks the link or the notice omits a required element.
- Reference: SD Elements guidance for T752.

**Success Criteria:**
- [ ] Vitest tests pass for all main routes, including unauthenticated ones.
- [ ] Privacy page contains the four required sections.
- [ ] Notice version change re-prompts users (backend test).
- [ ] `consents` rows provide evidence of notification.

**Status:** Pending
