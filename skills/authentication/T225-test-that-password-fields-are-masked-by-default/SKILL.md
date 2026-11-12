---
name: t225-test-that-password-fields-are-masked-by-default
description: Test that every password entry point in the ACME Clinical React frontend (login, reset, profile change, staff onboarding) renders masked by default and only reveals on explicit user action, verifying T12.
---

# T225: Test that password fields are masked by default

**Category:** CODE_FIX
**SD Elements:** [T225](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T225/)
**Priority:** 2/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Several screens (login, password recovery, profile) collect passwords. A new screen could easily use a plain `<input>` instead of the shared `PasswordField` component, and no one would notice without a test.

**Secure Implementation Pattern:**
```tsx
// frontend/src/screens/passwordMasking.test.tsx  (vitest + @testing-library/react)
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { LoginScreen } from './Login';
import { ResetPasswordScreen } from './ResetPassword';
import { ProfileScreen } from './Profile';

const screens = { LoginScreen, ResetPasswordScreen, ProfileScreen };

describe.each(Object.entries(screens))('%s', (_name, Screen) => {
  it('masks every password input by default', () => {
    const { container } = render(<MemoryRouter><Screen /></MemoryRouter>);
    const inputs = container.querySelectorAll('input[autocomplete$="password"]');
    expect(inputs.length).toBeGreaterThan(0);
    inputs.forEach((el) => expect(el).toHaveAttribute('type', 'password'));
  });

  it('reveals only after explicit toggle', async () => {
    render(<MemoryRouter><Screen /></MemoryRouter>);
    const [toggle] = screen.getAllByRole('button', { name: /show password/i });
    await userEvent.click(toggle);
    expect(screen.getAllByDisplayValue('').some((el) => el.getAttribute('type') === 'text')).toBe(true);
  });
});
```

**Implementation Guidance:**
- Inventory every place a password is entered: Login, Reset Password, Profile change password, first password for invited staff, and any admin dialog. Add each to the `screens` map.
- Add an ESLint `no-restricted-syntax` rule, or a test that scans `frontend/src` for `<input` elements whose name, id or autocomplete matches `password` outside `PasswordField.tsx`.
- Manual: type a password on each screen of the Vercel deployment and confirm that it is masked until "Show password" is clicked.
- Reference: SD Elements guidance for T225.

**Success Criteria:**
- [ ] The Vitest suite passes for every password-entry screen.
- [ ] No raw password `<input>` exists outside `PasswordField` (lint or test check).

**Status:** Applied
