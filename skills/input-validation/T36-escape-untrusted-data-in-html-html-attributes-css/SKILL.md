---
name: t36-escape-untrusted-data-in-html-html-attributes-css
description: Contextually escape untrusted data (patient names, observations, alarm notes, ward and device names, error messages) in the ACME Clinical React frontend and in Python-generated report/CSV output, relying on React's auto-escaping and forbidding raw HTML sinks.
---

# T36: Escape untrusted data in HTML, HTML attributes, CSS, and JavaScript

**Category:** CODE_FIX
**SD Elements:** [T36](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T36/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow linking a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Observations, alarm acknowledgement notes, staff names and device labels are free text entered by one user and displayed to many (ward overview, patient detail, reports, realtime alarm banner). A developer wanting "rich" notes may render them with `dangerouslySetInnerHTML`, build `style` strings or `href`s from data, or display server error text as HTML, causing stored XSS that runs with a clinician's Supabase session.

**Secure Implementation Pattern:**
```tsx
// frontend/src/components/ObservationText.tsx
export function ObservationText({ text }: { text: string }) {
  // React escapes text children; keep line breaks via CSS, not HTML
  return <p style={{ whiteSpace: "pre-wrap" }}>{text}</p>;
}

// Attributes: static attribute names; values from data are text, never handlers/URLs
<VitalSignTile label={vital.label} title={patient.displayName} />

// URLs from data go through a scheme allowlist (see frontend/src/components/ExternalLink.tsx)
const safeHref = (u: string) => { try { const p = new URL(u, window.location.origin);
  return ["https:", "http:"].includes(p.protocol) ? p.href : "#"; } catch { return "#"; } };

// CSS: no data in style strings except validated numbers/enums
const color = { high: "var(--alarm-high)", medium: "var(--alarm-med)", low: "var(--alarm-low)" }[alarm.priority];
```
```python
# backend/app/services/reports.py - CSV is also an output context (formula injection)
def csv_safe(value) -> str:
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s
```

**Implementation Guidance:**
- In `frontend/src/screens/*.tsx` and `frontend/src/components/*.tsx`, render all API/Realtime data as JSX text children or plain attribute values; ban `dangerouslySetInnerHTML`, `innerHTML`, `eval`, `new Function` and `javascript:` URLs (ESLint `react/no-danger`, `no-eval`, `no-implied-eval`).
- Display error messages from `frontend/src/components/ErrorMessage.tsx` as text only; the backend error envelope (`backend/app/core/errors.py`) must not echo raw input.
- Route any link built from data through `frontend/src/components/ExternalLink.tsx` (scheme allowlist, `rel="noopener noreferrer"`).
- Never interpolate data into `style` strings or CSS `url()`; map enums to CSS variables.
- Python outputs: keep `csv_safe` in `backend/app/services/reports.py` applied to every exported cell; JSON responses are `application/json` so browsers never render them as HTML.
- Keep the strict CSP in `frontend/vercel.json` (`script-src 'self'`) as defence in depth.
- Reference: SD Elements guidance for T36.

**Success Criteria:**
- [ ] `grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" frontend/src` returns no production usage.
- [ ] Vitest in `frontend/src/security.test.tsx`: an observation `<img src=x onerror=alert(1)>` renders as literal text and creates no `img` element.
- [ ] Pytest: CSV export of a value `=HYPERLINK(...)` is prefixed with `'`.

**Status:** Pending
