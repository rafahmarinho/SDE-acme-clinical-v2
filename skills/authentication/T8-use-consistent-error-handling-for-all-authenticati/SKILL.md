---
name: t8-use-consistent-error-handling-for-all-authenticati
description: Makes every ACME Clinical authentication failure (login, password recovery, lockout, unknown email) return the same generic message, response shape and timing, so staff accounts cannot be enumerated.
---

# T8: Use Consistent Error Handling for All Authentication Failures

**Category:** CODE_FIX
**SD Elements:** [T8](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T8/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca, filtros, estados de carregamento e mensagens de erro."
> (EN: Include login, password recovery, profile, settings, search, filters, loading states and error messages.)
> Source: specs/PRD.md, lines 11-13

**What the spec implies (naive approach):**
The PRD asks for helpful error messages, so a developer might show "No account with this email", "Wrong password" or "Email not confirmed", or pass Supabase's raw `error.message` straight to the user. Each distinct message, or a different HTTP status, tells an attacker which clinician emails exist.

**Secure Implementation Pattern:**
```typescript
// frontend/src/services/auth.ts
import { supabase } from '../lib/supabase';

export const GENERIC_LOGIN_ERROR = 'Email or password is incorrect.';
export const GENERIC_RESET_MSG =
  'If an account exists for this email, a password reset link has been sent.';

export async function login(email: string, password: string, captchaToken: string) {
  const { data, error } = await supabase.auth.signInWithPassword({
    email: email.trim().toLowerCase(), password, options: { captchaToken },
  });
  if (error) {
    // Never surface error.message / error.code: unknown user, bad password,
    // soft lock and unconfirmed email all look identical to the user.
    console.debug('auth failure', error.status);   // no email, no password
    throw new Error(GENERIC_LOGIN_ERROR);
  }
  return data.session;
}

export async function requestReset(email: string, captchaToken: string) {
  await supabase.auth.resetPasswordForEmail(email.trim().toLowerCase(), {
    redirectTo: `${window.location.origin}/reset-password`, captchaToken,
  }).catch(() => undefined);           // swallow: identical outcome either way
  return GENERIC_RESET_MSG;
}
```

**Implementation Guidance:**
- Keep the generic messages in `frontend/src/services/auth.ts`. Login and reset screens in `frontend/src/screens/` only render them, and rate-limit or CAPTCHA errors also map to the generic text with a "try again later" hint.
- Backend auth-related endpoints (staff invite, password change, `/me`) return a uniform `{"detail": "Authentication failed"}` with 401 from one exception handler in `backend/app/core/errors.py`, and never tell "token expired" apart from "user not found" in the body.
- Do not set app cookies or local storage keys before login that differ by account existence. supabase-js stores the session only after success.
- Add a fixed minimum response time with jitter to app-owned auth endpoints (T73).
- Do not add a "personal image or phrase" step after entering the email.
- Reference: SD Elements guidance for T8.

**Success Criteria:**
- [ ] Login with an unknown email and with a known email plus wrong password shows the same text, and the backend returns identical status and body.
- [ ] Password reset shows the same confirmation for existing and non-existing emails.
- [ ] Vitest `frontend/src/services/auth.test.ts` mocks supabase errors (`invalid_credentials`, `email_not_confirmed`, `user_banned`) and checks that all of them produce `GENERIC_LOGIN_ERROR`.

**Status:** Pending
