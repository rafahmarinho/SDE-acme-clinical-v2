---
name: t37-avoid-dom-based-cross-site-scripting-xss
description: Avoid DOM-based XSS in the ACME Clinical React SPA by never feeding location, hash, query, referrer or Supabase recovery-link parameters into HTML, script or URL sinks, and by validating post-login redirect targets.
---

# T37: Avoid DOM-based Cross-Site Scripting (XSS)

**Category:** CODE_FIX
**SD Elements:** [T37](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T37/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: services and database access. Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Login with `?next=` redirects, password recovery links that land on `/reset-password#access_token=...&error_description=...`, and search/filter state stored in the query string are all attacker-controllable DOM sources. Naive code shows `error_description` with `innerHTML`, does `window.location = params.get("next")`, or echoes the search term into the DOM, creating DOM XSS or `javascript:` redirects.

**Secure Implementation Pattern:**
```ts
// frontend/src/lib/safeNext.ts
export function safeNext(raw: string | null, fallback = "/"): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return fallback;
  try {
    const u = new URL(raw, window.location.origin);
    return u.origin === window.location.origin ? u.pathname + u.search + u.hash : fallback;
  } catch { return fallback; }
}

// frontend/src/screens/ResetPassword.tsx - show recovery errors as text, from an allowlist
const KNOWN = { otp_expired: "This reset link has expired. Request a new one." } as const;
const code = new URLSearchParams(window.location.hash.slice(1)).get("error_code");
const message = (code && KNOWN[code as keyof typeof KNOWN]) ?? (code ? "The reset link is invalid." : null);

// Search term from ?q= is controlled-input state, rendered as text only
const [q, setQ] = useState(() => new URLSearchParams(location.search).get("q")?.slice(0, 100) ?? "");
```

**Implementation Guidance:**
- Treat `window.location.*`, `document.referrer`, `URLSearchParams`, route params and the Supabase auth URL fragment as untrusted in `frontend/src/screens/Login.tsx`, `ResetPassword.tsx`, `ForgotPassword.tsx`, `PatientList.tsx` and `frontend/src/components/SearchFilterBar.tsx`.
- All redirects after login/re-auth go through `frontend/src/lib/safeNext.ts` (same-origin path only); never assign untrusted values to `location`, `href`, `src` or `formAction`.
- Never use `innerHTML`/`outerHTML`/`document.write`/`insertAdjacentHTML`, `setAttribute("on*")`, `eval` or `setTimeout(string)`; React JSX text children are the safe sink.
- Map URL-supplied error codes to fixed messages instead of displaying `error_description`.
- Clear the recovery token fragment with `history.replaceState` after Supabase consumes it.
- Keep CSP `script-src 'self'` and consider `require-trusted-types-for 'script'` in `frontend/vercel.json`.
- Reference: SD Elements guidance for T37.

**Success Criteria:**
- [ ] `frontend/src/lib/safeNext.test.ts` covers `//evil.com`, `/\evil.com`, `javascript:alert(1)`, `https://evil.com` (all fall back to `/`).
- [ ] Vitest (`frontend/src/screens/auth.test.tsx`): `/reset-password#error_description=<img src=x onerror=alert(1)>` renders no injected element.
- [ ] No DOM HTML sinks in `frontend/src` (lint rule enforced in CI).

**Status:** Pending
