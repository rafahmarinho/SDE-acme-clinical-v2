---
name: t1468-encrypt-sensitive-data-at-rest-in-the-browser
description: Keep PHI and tokens out of persistent browser storage in the ACME Clinical SPA (no patient data in localStorage/IndexedDB, Supabase session in sessionStorage only), and if anything sensitive must be stored, encrypt it with a non-extractable in-memory WebCrypto AES-GCM key.
---

# T1468: Encrypt sensitive data at rest in the browser

**Category:** CODE_FIX
**SD Elements:** [T1468](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1468/)
**Priority:** 9/10 · **Phase:** requirements

**Spec Context:**
> "devem aparecer nas telas e continuar salvos após recarregar a aplicação. Entregue o código"
> (EN: must appear on the screens and remain saved after reloading the application. Deliver the code)
> Source: specs/PRD.md, line 45

**What the spec implies (naive approach):**
"Remain saved after reloading" can be misread as "cache it in the browser": developers store patient lists, vitals, observations or the Supabase refresh token in `localStorage`/IndexedDB in plain text. Anyone with access to a shared ward workstation, a browser profile backup or an XSS can read it. The requirement is met by persisting data in Supabase, not in the browser.

**Secure Implementation Pattern:**
```ts
// frontend/src/lib/supabase.ts - auth session only in sessionStorage (tab-scoped), never PHI
export const supabase = createClient(url, anonKey, {
  auth: { storage: sessionStore(), persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
});

// frontend/src/lib/secureStore.ts - ONLY if something sensitive must survive a reload (e.g. an unsent draft)
let key: CryptoKey | null = null;                                   // memory only, non-extractable
async function getKey() {
  return (key ??= await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]));
}
export async function putEncrypted(name: string, value: unknown) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await getKey(),
                                         new TextEncoder().encode(JSON.stringify(value)));
  sessionStorage.setItem(`enc:${name}`, JSON.stringify({ iv: Array.from(iv), ct: Array.from(new Uint8Array(ct)) }));
}
// Key is lost when the tab closes => data becomes unreadable by design; clear on logout (T1539).
```

**Implementation Guidance:**
- Inventory browser storage use in `frontend/src` (`localStorage`, `sessionStorage`, IndexedDB, Cache API, service workers); only non-sensitive UI preferences may be stored in plain text.
- Keep the Supabase session in `sessionStorage` via `sessionStore()` in `frontend/src/lib/supabase.ts` (documented in `docs/security/sessions.md`); do not persist refresh tokens in `localStorage`.
- PHI (patient names, vitals, observations, reports) lives in React state/memory only and is re-fetched from the API after reload; offline access is not a requirement, so no PWA cache.
- If a justified case arises, centralise encryption in one module (`frontend/src/lib/secureStore.ts`) using WebCrypto AES-GCM with a random 96-bit IV and a non-extractable key held in memory (or derived from a server-provided key per T1468 guidance); never roll custom crypto (T59).
- Downloads of reports/attachments use short-lived signed URLs, not blobs stored in IndexedDB.
- Reference: SD Elements guidance for T1468.

**Success Criteria:**
- [ ] `grep -rn "localStorage" frontend/src` shows no PHI or token writes.
- [ ] Vitest (`frontend/src/auth/supabaseClient.test.ts`): the Supabase client is configured with session-scoped storage; after login, `localStorage` has no `sb-*-auth-token`.
- [ ] Manual check (DevTools > Application) after browsing patients shows no patient data in any storage area.

**Status:** Applied
