---
name: t420-prevent-client-side-template-injection-csti
description: Prevents client-side template injection in the ACME Clinical React frontend by relying on JSX auto-escaping, banning eval/new Function/dangerouslySetInnerHTML on user data, and never mixing server-rendered templates with client templates.
---

# T420: Prevent Client-Side Template Injection (CSTI)

**Category:** CODE_FIX
**SD Elements:** [T420](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T420/)
**Priority:** 6/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow linking a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Observations, staff names and alarm notes are user-authored text shown on patient detail and ward screens. A developer may add "rich" formatting with `dangerouslySetInnerHTML`, a markdown library with HTML enabled, a client template engine (Handlebars/lodash `template`) or `eval` for formula-like threshold expressions, enabling script or expression injection.

**Secure Implementation Pattern:**
```tsx
// frontend/src/components/ObservationItem.tsx
type Props = { author: string; text: string; createdAt: string };

export function ObservationItem({ author, text, createdAt }: Props) {
  // JSX escapes {text}; whitespace preserved via CSS, no HTML parsing.
  return (
    <li className="observation">
      <span className="author">{author}</span>
      <time dateTime={createdAt}>{new Date(createdAt).toLocaleString("en-US")}</time>
      <p style={{ whiteSpace: "pre-wrap" }}>{text}</p>
    </li>
  );
}
```
```json
// frontend/eslint.config rules (excerpt)
{
  "rules": {
    "no-eval": "error",
    "no-implied-eval": "error",
    "no-new-func": "error",
    "react/no-danger": "error"
  }
}
```

**Implementation Guidance:**
- Render all user data through JSX expressions in `frontend/src/components` and `frontend/src/screens`; do not use `dangerouslySetInnerHTML`, `innerHTML`, or client template libraries that compile user strings.
- Never pass user input to `eval`, `new Function`, `setTimeout(string)` or dynamic `import()`; threshold or scenario logic lives in the Python backend.
- If markdown is ever needed, use a renderer with HTML disabled plus DOMPurify; do not rely on sandboxes.
- Do not mix server-side templates with the client: the FastAPI backend returns JSON only, never HTML fragments containing user data for the SPA to inject.
- Validate inputs server-side as in T31.
- Reference: SD Elements guidance for T420.

**Success Criteria:**
- [ ] ESLint with `no-eval`, `no-new-func`, `react/no-danger` passes in CI with zero violations.
- [ ] `grep -r "dangerouslySetInnerHTML\|innerHTML\|new Function" frontend/src` returns no matches on user data paths.
- [ ] Vitest: rendering an observation `{{constructor.constructor('alert(1)')()}}` or `<img src=x onerror=alert(1)>` shows the literal text.

**Status:** Pending
