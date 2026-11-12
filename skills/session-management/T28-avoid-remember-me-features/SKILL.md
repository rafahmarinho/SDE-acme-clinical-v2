---
name: t28-avoid-remember-me-features
description: Do not offer a "remember me" login in ACME Clinical; keep the Supabase session in sessionStorage so it survives a page reload but not closing the browser, and require re-authentication for critical actions such as password, email or role changes.
---

# T28: Avoid 'Remember Me' features

**Category:** CODE_FIX
**SD Elements:** [T28](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T28/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "devem aparecer nas telas e continuar salvos após recarregar a aplicação."
> (EN: must appear on the screens and remain saved after reloading the application.)
> Source: specs/PRD.md, line 45

> "Quero desenvolver esta aplicação, com aparência e funcionamento próximos de um produto real."
> (EN: I want to develop this application with a look and behaviour close to a real product.)
> Source: specs/PRD.md, line 1

**What the spec implies (naive approach):**
"Remain saved after reloading" is about *data* (simulation results, observations, acknowledgements) persisted in Supabase PostgreSQL. A developer aiming for a "real product" feel would add a "Remember me" checkbox and keep the `supabase-js` default (`localStorage`, auto-refresh), so the session survives closing the browser and the next person at a shared ward workstation is automatically logged in as the previous clinician.

**Secure Implementation Pattern:**
```typescript
// frontend/src/lib/supabase.ts
export const supabase = createClient(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY, {
  auth: {
    storage: window.sessionStorage,   // survives reload (PRD), cleared when the tab/browser closes
    persistSession: true,
    autoRefreshToken: true,
    flowType: "pkce",
  },
});

// frontend/src/screens/Login.tsx: no "Remember me" checkbox.
// Allowed: remember the last e-mail address (non-secret) if the user opts in.
localStorage.setItem("acme.lastEmail", email);   // never tokens, never patient data

// Critical actions require fresh credentials (reauthenticate)
export async function confirmPassword(email: string, password: string) {
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw new Error("Re-authentication failed");
}
```

**Implementation Guidance:**
- Keep data persistence and session persistence separate: data persists in Supabase (satisfies line 45); the session persists only in `sessionStorage`, so a reload keeps the user signed in but closing the browser ends it. Server-side absolute (T25) and idle (T24) timeouts still apply.
- Do not use `localStorage` or a persistent cookie for auth tokens. If the optional FastAPI refresh cookie is used, omit `expires`/`max_age` so it is a non-persistent session cookie.
- Remove any "Remember me" / "Keep me signed in" control from `frontend/src/screens/Login*`.
- Require re-authentication (password re-entry, or Supabase "Secure password change", which requires a recent login or nonce via `supabase.auth.reauthenticate()`) for: changing password or email (Profile), changing staff roles (team management), changing alarm thresholds, and resetting simulation data. The backend (`backend/app/core/security.py`) enforces this by requiring the session's last authentication time (JWT `amr` timestamp) to be under 5 minutes old for these routes.
- Reference: SD Elements guidance for T28.

**Success Criteria:**
- [ ] The login screen has no remember-me option.
- [ ] Reloading keeps the session; closing and reopening the browser requires login.
- [ ] No auth token is found in `localStorage` or in persistent cookies.
- [ ] Password/email/role/threshold changes fail with `401 reauth_required` unless the user re-authenticated within 5 minutes.
- [ ] Tests described in T95.

**Status:** Pending
