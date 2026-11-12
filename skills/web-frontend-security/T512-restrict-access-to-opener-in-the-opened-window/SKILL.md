---
name: t512-restrict-access-to-opener-in-the-opened-window
description: Prevents reverse tabnabbing in the ACME Clinical SPA by ensuring every new window or tab (report downloads, Supabase Storage signed URLs, device manuals, 3D view pop-outs) is opened with noopener/noreferrer and no opener reference.
---

# T512: Restrict access to opener in the opened window

**Category:** CODE_FIX
**SD Elements:** [T512](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T512/)
**Priority:** 4/10 · **Phase:** development

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Reports and stored files are likely opened in a new tab (`target="_blank"` or `window.open(signedUrl)`), and device/maintenance records may link to external manufacturer pages. If the opened page can access `window.opener`, it can redirect the logged-in ACME Clinical tab to a phishing login page.

**Secure Implementation Pattern:**
```tsx
// frontend/src/components/ExternalLink.tsx
import { AnchorHTMLAttributes } from "react";

export function ExternalLink(props: AnchorHTMLAttributes<HTMLAnchorElement>) {
  return <a {...props} target="_blank" rel="noopener noreferrer" />;
}

// frontend/src/lib/openWindow.ts
export function openSafely(url: string): void {
  const u = new URL(url, window.location.origin);
  if (u.protocol !== "https:" && u.origin !== window.location.origin) {
    throw new Error("Blocked non-HTTPS URL");
  }
  const w = window.open(u.toString(), "_blank", "noopener,noreferrer");
  if (w) w.opener = null; // belt and braces for older engines
}
```

```json
{ "key": "Cross-Origin-Opener-Policy", "value": "same-origin" }
```

**Implementation Guidance:**
- Use `ExternalLink` for every `target="_blank"` link in `frontend/src/components` and `frontend/src/screens`; add ESLint rule `react/jsx-no-target-blank` (error) to block raw usage.
- Use `openSafely()` from `frontend/src/lib` for report downloads (Supabase Storage signed URLs) and any pop-out windows (e.g. 3D ward view).
- Any user-entered URL (e.g. a link in device maintenance notes) must be rendered via `ExternalLink` and only for `https:` schemes.
- Add `Cross-Origin-Opener-Policy: same-origin` to `frontend/vercel.json` headers as an extra browser-level isolation.
- Reference: SD Elements guidance for T512.

**Success Criteria:**
- [ ] No `target="_blank"` without `rel="noopener noreferrer"` in `frontend/src` (ESLint passes).
- [ ] All `window.open` calls go through `openSafely`.
- [ ] Verification test in T513 passes.

**Status:** Pending
