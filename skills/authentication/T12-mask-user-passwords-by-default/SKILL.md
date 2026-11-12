---
name: t12-mask-user-passwords-by-default
description: Ensures every password input in the ACME Clinical React frontend (login, password recovery, profile change, staff onboarding) is masked by default, with an optional accessible show/hide toggle.
---

# T12: Mask User Passwords by Default

**Category:** CODE_FIX
**SD Elements:** [T12](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T12/)
**Priority:** 2/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Password fields built with generic text input components, or with a "show password" toggle that starts in the visible state, expose credentials on shared ward workstations and large nursing-station displays where others can see the screen.

**Secure Implementation Pattern:**
```tsx
// frontend/src/components/PasswordField.tsx
import { useId, useState } from 'react';

type Props = { label: string; value: string; onChange: (v: string) => void;
               autoComplete: 'current-password' | 'new-password' };

export function PasswordField({ label, value, onChange, autoComplete }: Props) {
  const [visible, setVisible] = useState(false);          // masked by default
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} type={visible ? 'text' : 'password'} value={value}
             autoComplete={autoComplete} spellCheck={false} autoCapitalize="off"
             onChange={(e) => onChange(e.target.value)}
             onBlur={() => setVisible(false)} />          {/* re-mask when leaving the field */}
      <button type="button" aria-pressed={visible} aria-controls={id}
              onClick={() => setVisible((v) => !v)}>
        {visible ? 'Hide password' : 'Show password'}
      </button>
    </div>
  );
}
```

**Implementation Guidance:**
- Use `PasswordField` from `frontend/src/components/` for every password input: Login, Reset Password, Profile change password (current, new, confirm) and invited-staff first password.
- Default `type="password"`. Showing is an explicit user action and re-masks on blur and on submit.
- Use `autoComplete="current-password"` or `"new-password"` so password managers work, and disable spellcheck so cloud spellcheckers do not receive the value.
- Never echo passwords in toasts, error messages, the React Query cache, logs or analytics.
- Reference: SD Elements guidance for T12.

**Success Criteria:**
- [ ] Every password input renders with `type="password"` on first paint.
- [ ] Vitest and Testing Library test `frontend/src/components/PasswordField.test.tsx` checks the default `type=password`, that the toggle switches to text, and that blur re-masks.

**Status:** Pending
