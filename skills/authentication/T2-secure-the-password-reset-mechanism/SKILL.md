---
name: t2-secure-the-password-reset-mechanism
description: Harden the ACME Clinical password recovery flow (Supabase Auth recovery e-mail, ForgotPassword and ResetPassword screens) so it resists automation and enumeration, uses short-lived single-use links, offers global sign-out and sends a change confirmation without revealing the password.
---

# T2: Secure the password reset mechanism

**Category:** CODE_FIX
**SD Elements:** [T2](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T2/)
**Priority:** 9/10 · **Phase:** requirements

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: services and database access. Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
"Include password recovery" is typically satisfied by calling `supabase.auth.resetPasswordForEmail()` and showing "No account with that e-mail" when it fails. That leaks which clinical staff accounts exist, lets bots trigger unlimited recovery e-mails, keeps old sessions alive after the reset, and may leave long-lived recovery links in mailboxes.

**Secure Implementation Pattern:**
```tsx
// frontend/src/screens/ForgotPassword.tsx - same confirmation for every input, anti-automation token
async function onSubmit(e: FormEvent) {
  e.preventDefault();
  setBusy(true);
  try {
    await supabase.auth.resetPasswordForEmail(canonicalEmail(email), {
      redirectTo: `${window.location.origin}/reset-password`,
      captchaToken,                       // Turnstile/hCaptcha token once [auth.captcha] is enabled
    });
  } catch { /* swallow: never reveal whether the account exists */ }
  setSent(true);                          // "If an account exists, we have sent instructions."
  setBusy(false);
}

// frontend/src/screens/ResetPassword.tsx - after a successful update, end every other session
const { error } = await supabase.auth.updateUser({ password: newPassword });
if (!error && signOutEverywhere) await supabase.auth.signOut({ scope: "global" });
```
```toml
# supabase/config.toml
[auth.email]
otp_expiry = 900            # recovery links valid 15 minutes, single use
max_frequency = "60s"
[auth.captcha]
enabled = true
provider = "turnstile"
```

**Implementation Guidance:**
- Keep the uniform confirmation page in `frontend/src/screens/ForgotPassword.tsx`: the same message, status and timing whether the address exists or not (no cookies or state that differ by input).
- Close the anti-automation gap: `supabase/config.toml` currently has `[auth.captcha] enabled = false`; add a Turnstile/hCaptcha widget (with an accessible alternative) to `ForgotPassword.tsx` and `Login.tsx`, pass `captchaToken`, enable `[auth.captcha]`, and allow the widget origin in the CSP in `frontend/vercel.json`.
- Reduce `otp_expiry` (currently 3600 s) to 15-30 minutes so recovery links expire quickly; keep `[auth.rate_limit] email_sent` and `token_verifications` limits and the lockout hook in `supabase/migrations/0006_auth.sql`.
- The PRD flow uses e-mail links instead of security questions; do not add knowledge-based questions. The emailed link plus the lockout/rate limits stand in for steps 3-4 of the guidance.
- In `frontend/src/screens/ResetPassword.tsx`, validate the new password against the shared policy (`frontend/src/lib/authPolicy.ts`, `backend/app/services/passwords.py`) and offer (default on) "sign out on all devices" via `signOut({ scope: "global" })`.
- Configure the Supabase "password changed" notification e-mail template so users are told about the change; templates must never contain the password.
- Restrict `redirectTo` to the exact allow-listed URLs in `supabase/config.toml` (`additional_redirect_urls`).
- Reference: SD Elements guidance for T2.

**Success Criteria:**
- [ ] `frontend/src/screens/auth.test.tsx`: ForgotPassword renders the identical confirmation for an existing address, an unknown address and a thrown error.
- [ ] `backend/tests/test_authentication.py::test_supabase_auth_configuration_hardened` extended to assert `otp_expiry <= 1800`, `[auth.captcha] enabled = true` and a non-zero `email_sent` rate limit.
- [ ] Vitest: after a successful reset with "sign out everywhere" checked, `supabase.auth.signOut` is called with `{ scope: "global" }`.
- [ ] Manual check: a recovery link used twice, or after expiry, is rejected; the confirmation e-mail does not contain the password.

**Status:** Pending
