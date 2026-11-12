---
name: t89-test-that-site-is-not-vulnerable-to-xss
description: Test recipe injecting XSS meta-characters and script payloads into ACME Clinical parameters, headers, cookies and stored fields (observations, names, search, notes) and verifying they are encoded in the React UI, API responses and reports.
---

# T89: Test that site is not vulnerable to XSS

**Category:** CODE_FIX
**SD Elements:** [T89](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T89/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Search terms are echoed ("No results for ..."), profile names and observations are stored and displayed to other staff, and reports render patient data. Any spot using raw HTML (`dangerouslySetInnerHTML`, HTML reports without escaping, error pages reflecting input) becomes reflected or stored XSS.

**Secure Implementation Pattern:**
```tsx
// frontend/src/screens/__tests__/xss.test.tsx
import { render } from "@testing-library/react";
import { it, expect, vi } from "vitest";
import { PatientSearchResults } from "../PatientSearchResults";

const XSS = ["<script>alert('xss')</script>", "' onmouseover=alert(/XSS/) '",
             "javascript:alert('xss')", "<svg onload=alert(1)>", "\"><img src=x onerror=alert(1)>"];

it.each(XSS)("encodes %s", (p) => {
  const alert = vi.spyOn(window, "alert").mockImplementation(() => {});
  const { container } = render(<PatientSearchResults query={p} results={[{ id: "1", name: p }]} />);
  expect(container.querySelector("script,svg,img[onerror]")).toBeNull();
  container.querySelectorAll("a").forEach((a) => expect(a.getAttribute("href")).not.toMatch(/^javascript:/i));
  expect(alert).not.toHaveBeenCalled();
});
```
```python
# backend/tests/test_xss_api.py - API must not return HTML-interpreted content
async def test_error_not_reflected_as_html(client):
    r = await client.get("/api/patients", params={"search": "<script>alert(1)</script>"})
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers.get("x-content-type-options") == "nosniff"
```

**Implementation Guidance:**
- For each HTTP parameter name/value, header name/value and cookie name/value, send XSS meta-characters (`< > " ' & /`) and inspect the resulting page, JS and CSS for unencoded output; then try full payloads.
- Cover stored vectors: create observations, staff names, device names, alarm notes with payloads via the API and view them in every role's screens and generated reports.
- Controls verified: React JSX escaping, no `dangerouslySetInnerHTML`, URL attributes restricted to `http(s):`/relative, JSON-only API with `nosniff`, autoescaped report templates, CSP in `frontend/vercel.json`.
- Run in all supported browsers (Chrome, Firefox, Edge, Safari); optionally add an OWASP ZAP baseline scan in CI.
- Reference: SD Elements guidance for T89.

**Success Criteria:**
- [ ] Vitest XSS suites pass for search, patient detail, staff and alarm components.
- [ ] Manual/ZAP run documents no pop-up in any supported browser for reflected and stored payloads.

**Status:** Applied
