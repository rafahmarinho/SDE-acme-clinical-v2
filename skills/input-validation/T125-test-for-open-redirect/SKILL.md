---
name: t125-test-for-open-redirect
description: Test recipe verifying that ACME Clinical login, logout and Supabase password-recovery flows cannot redirect users to external sites through next/redirect/redirectTo parameters.
---

# T125: Test for open redirect

**Category:** CODE_FIX
**SD Elements:** [T125](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T125/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Login will usually return users to the page they came from (`/login?next=/patients/12`) and password recovery uses Supabase `resetPasswordForEmail(email, { redirectTo })`. If `next` or `redirectTo` is taken from the URL unchecked, a phishing link can send clinicians to a look-alike site after real authentication.

**Secure Implementation Pattern:**
```ts
// frontend/src/lib/__tests__/redirect.test.ts
import { describe, it, expect } from "vitest";
import { safeNext } from "../redirect";

const EVIL = ["http://www.google.com", "//evil.example", "/\\evil.example", "https:evil.example",
              "javascript:alert(1)", "/%2F%2Fevil.example", "\t//evil.example", "https://acme-clinical.vercel.app.evil.example"];

describe("open redirect", () => {
  it.each(EVIL)("rejects %s", (n) => expect(safeNext(n)).toBe("/"));
  it("keeps internal paths", () => expect(safeNext("/patients/12?tab=vitals")).toBe("/patients/12?tab=vitals"));
});
```
```text
Manual: open {FRONTEND}/login?next=https://www.google.com, sign in as nurse@demo -> must land on an
internal page. Request password reset with a modified redirectTo -> Supabase must refuse URLs not on
the project's Redirect URLs allow-list.
```

**Implementation Guidance:**
- Enumerate redirect inputs: `next`/`returnTo` on login, post-logout target, Supabase `redirectTo`/`emailRedirectTo` for recovery and invites, any backend `RedirectResponse`.
- Try external URLs and bypass encodings (protocol-relative, backslashes, encoded slashes, whitespace prefixes, look-alike subdomains); the test fails if the browser leaves the app's origin after login.
- Verify the Supabase Auth "Redirect URLs" allow-list contains only the production and preview frontend origins.
- Record any legitimately allowed external redirects and confirm with developers.
- Reference: SD Elements guidance for T125.

**Success Criteria:**
- [ ] Vitest suite for `safeNext` passes with all bypass payloads.
- [ ] Manual login and password-recovery tests documented with no external redirection.

**Status:** Pending
