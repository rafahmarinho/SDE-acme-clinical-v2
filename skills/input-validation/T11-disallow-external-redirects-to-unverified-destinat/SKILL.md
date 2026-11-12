---
name: t11-disallow-external-redirects-to-unverified-destinat
description: Prevents open redirects in ACME Clinical by allowing only same-origin relative paths after login and fixed, allow-listed redirectTo URLs for Supabase password recovery, never user-supplied destinations.
---

# T11: Disallow external redirects to unverified destinations

**Category:** CODE_FIX
**SD Elements:** [T11](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T11/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A developer would pass `searchParams.get("next")` straight to `navigate()`/`window.location`, and set Supabase `redirectTo: window.location.origin + params.get("redirect")` for recovery emails. Both let an attacker craft links that land authenticated users on external phishing pages.

**Secure Implementation Pattern:**
```ts
// frontend/src/lib/redirect.ts
const APP_ORIGIN = window.location.origin;
const ALLOWED_PREFIXES = ["/wards", "/patients", "/monitoring", "/alarms", "/devices",
                          "/settings", "/reports", "/staff", "/simulation", "/profile"];

export function safeNext(raw: string | null | undefined): string {
  if (!raw) return "/";
  const v = raw.trim();
  if (!v.startsWith("/") || v.startsWith("//") || v.includes("\\")) return "/";
  try {
    const u = new URL(v, APP_ORIGIN);
    if (u.origin !== APP_ORIGIN) return "/";
    if (!ALLOWED_PREFIXES.some((p) => u.pathname === p || u.pathname.startsWith(p + "/"))) return "/";
    return u.pathname + u.search + u.hash;
  } catch { return "/"; }
}

// frontend/src/services/auth.ts - fixed, env-configured target; not from user input
export const requestPasswordReset = (email: string) =>
  supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${import.meta.env.VITE_APP_URL}/reset-password`,
  });
```

**Implementation Guidance:**
- Do not compute destinations from direct user input; map to known internal routes (allow-list of path prefixes) and fall back to the role's home screen.
- Validate the full parsed URL (`new URL`) against the app origin; reject protocol-relative, backslash and non-HTTP schemes.
- Set Supabase `redirectTo`/`emailRedirectTo` from `VITE_APP_URL` only, and configure Supabase Auth Site URL and Redirect URLs allow-list to the production/preview frontend domains.
- In FastAPI, avoid `RedirectResponse` with request-derived URLs; if ever needed, use an id-to-URL mapping on the server.
- If an external link is ever required (e.g. device vendor manual), show an interstitial asking the user to confirm leaving ACME Clinical.
- Reference: SD Elements guidance for T11.

**Success Criteria:**
- [ ] All post-login and post-logout navigations go through `safeNext`.
- [ ] Supabase Redirect URLs allow-list contains only ACME Clinical frontend origins.
- [ ] Unit tests (see T125) reject external and encoded-bypass destinations.

**Status:** Pending
