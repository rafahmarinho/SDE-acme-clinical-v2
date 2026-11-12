---
name: t239-test-that-users-provide-consent-prior-to-the-colle
description: Test recipe confirming ACME Clinical shows a privacy notice and records staff acknowledgement/consent before collecting personal data at login, first profile setup and staff onboarding, and that declining blocks collection.
---

# T239: Test that users provide consent prior to the collection of personal information

**Category:** CODE_FIX
**SD Elements:** [T239](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T239/)
**Priority:** 10/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
The login and profile screens collect staff email, name and phone, but the PRD never mentions a privacy notice or consent. A naive implementation collects profile data on first login with no link to a privacy policy and no way to decline. Patient health data is processed under the care relationship (not consent), which must also be stated in the notice.

**Secure Implementation Pattern:**
```typescript
// frontend/src/screens/__tests__/consent.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProfileSetupScreen } from "../ProfileSetupScreen";
import { LoginScreen } from "../LoginScreen";

it("links the privacy notice on the login screen before any data entry", () => {
  render(<LoginScreen />);
  expect(screen.getByRole("link", { name: /privacy notice/i })).toHaveAttribute("href", "/privacy");
});

it("cannot submit profile data without acknowledging the notice", async () => {
  const save = vi.fn();
  render(<ProfileSetupScreen onSave={save} />);
  await userEvent.type(screen.getByLabelText(/full name/i), "Jane Doe");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  expect(save).not.toHaveBeenCalled();
  expect(screen.getByText(/acknowledge the privacy notice/i)).toBeVisible();
});
```

**Implementation Guidance:**
- Step 1: find every collection point: login (`frontend/src/screens/LoginScreen`), first profile setup, staff invite form in team management, observation entry.
- Step 2: assert a "Privacy notice" link (T751) is visible before data entry on each.
- Step 3: assert the optional fields (phone, avatar) can be declined and the consent checkbox is unchecked by default; record acceptance in `consents` table (user_id, notice_version, accepted_at) via `backend/app/routers/profile.py`.
- Step 4: backend test (`backend/tests/test_consent.py`): `PUT /me/profile` without a recorded acknowledgement of the current notice version returns 409.
- Reference: SD Elements guidance for T239.

**Success Criteria:**
- [ ] Vitest tests confirm notice link present on login and profile setup, and submission blocked without acknowledgement.
- [ ] Backend rejects profile writes before acknowledgement of the current notice version.
- [ ] Declining optional fields does not block account use.
- [ ] `consents` rows store notice version and timestamp.

**Status:** Pending
