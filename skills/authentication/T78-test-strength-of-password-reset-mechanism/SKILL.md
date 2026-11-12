---
name: t78-test-strength-of-password-reset-mechanism
description: Security tests for ACME Clinical's Supabase password recovery ("recuperação de senha") flow, covering anti-automation, non-enumerating responses, no plaintext passwords in email, single-use expiring links and no security questions.
---

# T78: Test strength of password reset mechanism

**Category:** CODE_FIX
**SD Elements:** [T78](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T78/)
**Priority:** 9/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A "Forgot password" screen would call `resetPasswordForEmail` and show "Email not found" for unknown addresses, with no CAPTCHA. Customized email templates might include a temporary password, and the redirect URL could be left open. All of these weaken account recovery for clinical staff.

**Secure Implementation Pattern:**
```typescript
// frontend/src/services/auth.test.ts (vitest) - response uniformity and anti-automation wiring
import { describe, it, expect, vi } from 'vitest';
import { requestReset, GENERIC_RESET_MSG } from './auth';
import { supabase } from '../lib/supabase';

describe('password reset', () => {
  it('returns the same message for unknown and known emails', async () => {
    const spy = vi.spyOn(supabase.auth, 'resetPasswordForEmail')
      .mockResolvedValueOnce({ data: {}, error: null } as never)
      .mockResolvedValueOnce({ data: null, error: { status: 400, message: 'User not found' } } as never);
    expect(await requestReset('nurse.demo@acme.test', 'tok')).toBe(GENERIC_RESET_MSG);
    expect(await requestReset('nobody@acme.test', 'tok')).toBe(GENERIC_RESET_MSG);
    expect(spy).toHaveBeenCalledWith(expect.any(String),
      expect.objectContaining({ captchaToken: 'tok' }));
  });
});
```
```python
# backend/tests/test_reset_config.py - config guardrails
import tomllib, pathlib
cfg = tomllib.loads(pathlib.Path("../supabase/config.toml").read_text())
def test_reset_hardening():
    auth = cfg["auth"]
    assert auth["captcha"]["enabled"] is True
    assert auth["rate_limit"]["email_sent"] <= 10
    assert auth["email"]["otp_expiry"] <= 3600
    assert all(u.startswith("https://") or "localhost" in u for u in auth["additional_redirect_urls"])
    tpl = pathlib.Path("../supabase/templates/recovery.html").read_text().lower()
    assert "password:" not in tpl and "{{ .confirmationurl }}" in tpl
```

**Implementation Guidance:**
- Step 1, anti-automation: submit 10 reset requests for invalid emails. Expect a CAPTCHA requirement and then 429 from Supabase `[auth.rate_limit]`. The test fails if requests keep going through.
- Step 2, email content: trigger a reset in local Supabase, open Inbucket or Mailpit (`supabase start`), and confirm that the email contains only a one-time link (no password) that expires within `otp_expiry` and fails on second use.
- Steps 3 and 4, security questions: ACME Clinical must not implement security questions. Document this as N/A by design.
- Step 5, cookies and storage: compare browser storage and cookies after resets for a valid and an invalid email. They must be identical (supabase-js stores nothing before login).
- Check the redirect allow-list: `redirectTo` must be the deployed frontend's `/reset-password` on Vercel, with no wildcard domains.
- Reference: SD Elements guidance for T78.

**Success Criteria:**
- [ ] Vitest and pytest checks above pass in CI.
- [ ] A manual test record (local Supabase Mailpit) confirms single-use, expiring links, no plaintext password, and 429 after repeated requests.

**Status:** Applied
