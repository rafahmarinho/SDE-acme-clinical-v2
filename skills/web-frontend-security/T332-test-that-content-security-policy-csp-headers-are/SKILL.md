---
name: t332-test-that-content-security-policy-csp-headers-are
description: Tests verifying that the ACME Clinical SPA and API send the expected Content-Security-Policy (default-src, script-src without unsafe-inline/eval, connect-src for API and Supabase https/wss, form-action, frame-ancestors, report-uri) and that the CSP report endpoint exists and logs violations.
---

# T332: Test that content security policy (CSP) headers are added

**Category:** CODE_FIX
**SD Elements:** [T332](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T332/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "README com os passos para rodar e publicar a versão web e a API na Vercel."
> (EN: README with the steps to run and publish the web version and the API on Vercel.)
> Source: specs/PRD.md, line 49

**What the spec implies (naive approach):**
The web app and API are published separately; CSP lives in `frontend/vercel.json` and in a FastAPI middleware. Without tests, a config edit can drop the header, add `unsafe-eval` for a library, or widen `connect-src`, and nobody notices.

**Secure Implementation Pattern:**
```typescript
// frontend/tests/csp.test.ts (vitest, parses vercel.json)
import { describe, it, expect } from "vitest";
import cfg from "../vercel.json";

const csp = cfg.headers.flatMap((h) => h.headers)
  .find((h) => h.key === "Content-Security-Policy")!.value;
const dir = (name: string) =>
  csp.split(";").map((d) => d.trim()).find((d) => d.startsWith(name + " ")) ?? "";

describe("frontend CSP", () => {
  it("has required directives", () => {
    ["default-src", "script-src", "connect-src", "form-action",
     "frame-ancestors", "object-src", "base-uri", "report-uri"]
      .forEach((d) => expect(dir(d), d).not.toBe(""));
  });
  it("script-src forbids inline and eval", () => {
    expect(dir("script-src")).not.toMatch(/unsafe-inline|unsafe-eval|\*/);
  });
  it("connect-src is an explicit allow-list", () => {
    expect(dir("connect-src")).toMatch(/wss:\/\/[a-z0-9]+\.supabase\.co/);
    expect(dir("connect-src")).not.toMatch(/\s\*|https:\s|wss:\s|\*\.vercel\.app/);
  });
});
```
```python
# backend/tests/test_csp.py
async def test_api_csp_and_report_endpoint(client):
    r = await client.get("/api/health")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    rep = await client.post("/api/csp-report", content=b'{"csp-report":{"violated-directive":"script-src"}}',
                            headers={"content-type": "application/csp-report"})
    assert rep.status_code == 204
```

**Implementation Guidance:**
- Add the vitest config test under `frontend/tests/` (enable `resolveJsonModule` in `tsconfig.json`) and the pytest under `backend/tests/`; they verify the control from T331 and the endpoint from T1469.
- Post-deploy manual check: open the production SPA, DevTools > Network > document > Response Headers, compare CSP to the expected value; exercise login, live monitoring (Realtime wss), reports and the 3D view and confirm no violations in the Console.
- Confirm a forced violation (e.g. in Preview, inject an inline script via DevTools) reaches `/api/csp-report` and is logged (sanitized).
- Reference: SD Elements guidance for T332.

**Success Criteria:**
- [ ] vitest CSP suite and pytest CSP suite pass in CI.
- [ ] Deployed responses match the configured policy; report endpoint returns 204 and logs the violation.

**Status:** Pending
