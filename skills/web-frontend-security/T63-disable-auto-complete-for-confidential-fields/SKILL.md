---
name: t63-disable-auto-complete-for-confidential-fields
description: Disables browser autocomplete on confidential ACME Clinical form fields (patient identifiers, clinical observations, patient search, password-reset tokens) on shared ward workstations, while deliberately keeping password-manager-compatible attributes on the login form per a documented risk decision.
---

# T63: Disable auto-complete for confidential fields

**Category:** CODE_FIX
**SD Elements:** [T63](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T63/)
**Priority:** 3/10 · **Phase:** development

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A developer would build login, patient search, observation and patient forms with default `<input>` elements. Browsers then remember patient names, identifiers and free-text observations typed on shared nursing-station computers and suggest them to the next user, leaking PHI.

**Secure Implementation Pattern:**
```tsx
// frontend/src/components/ConfidentialInput.tsx
import { forwardRef, InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & { label: string };

/** Use for patient identifiers, search boxes, observation fields. */
export const ConfidentialInput = forwardRef<HTMLInputElement, Props>(
  ({ label, id, ...rest }, ref) => (
    <label htmlFor={id}>
      {label}
      <input ref={ref} id={id} autoComplete="off" spellCheck={false}
             autoCorrect="off" autoCapitalize="off" {...rest} />
    </label>
  ),
);

// frontend/src/screens/ObservationForm.tsx (excerpt)
<form autoComplete="off" onSubmit={handleSubmit}>
  <ConfidentialInput id="obs-note" name="note" label="Observation" />
</form>

// frontend/src/screens/LoginScreen.tsx (risk decision: allow password managers)
<input type="email" name="email" autoComplete="username" />
<input type="password" name="password" autoComplete="current-password" />
// Reset password form: autoComplete="new-password"
```

**Implementation Guidance:**
- Create `ConfidentialInput` / `ConfidentialTextarea` in `frontend/src/components` and use them for: patient search (ward/patient list), patient identifiers, observation notes, limit configuration comments, team management user fields.
- Set `autoComplete="off"` on the `<form>` element too, so child inputs inherit it.
- Login and password reset: document the decision. Recommended: keep `autocomplete="username"`/`current-password`/`new-password` so password managers work (stronger passwords) and record this in `README`; if the organization's policy forbids it, use `autoComplete="off"` instead.
- Do not persist search terms or form drafts in `localStorage` (see T296).
- Reference: SD Elements guidance for T63.

**Success Criteria:**
- [ ] All patient-data fields and forms render with `autocomplete="off"`.
- [ ] The login form autocomplete decision is documented in `README`.
- [ ] A vitest/Testing Library test renders the observation form and patient search and asserts `autocomplete="off"` (see T111).

**Status:** Applied
