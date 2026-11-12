---
name: t132-test-for-standard-encoding-format-for-all-html-con
description: Tests verifying that every ACME Clinical HTML, text and report response declares the same character set (UTF-8) via the Content-Type header or meta charset.
---

# T132: Test for standard encoding format for all HTML content

**Category:** CODE_FIX
**SD Elements:** [T132](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T132/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "Use inglês como idioma padrão em todas as telas, mensagens, relatórios e dados de exemplo."
> (EN: Use English as the default language on all screens, messages, reports and sample data.)
> Source: specs/PRD.md, line 3

**What the spec implies (naive approach):**
Screens, messages and reports are produced by two codebases (Vite SPA and FastAPI report generation). Without a test, a new report endpoint could return `text/csv` or `text/html` without a charset, or a different one.

**Secure Implementation Pattern:**
```python
# backend/tests/test_charset.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

TEXT_ENDPOINTS = ["/api/reports/demo/export.csv", "/api/health"]

@pytest.mark.anyio
@pytest.mark.parametrize("path", TEXT_ENDPOINTS)
async def test_utf8_declared(path, auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        r = await c.get(path, headers=auth_headers)
    ct = r.headers["content-type"].lower()
    assert ct.startswith("application/json") or "charset=utf-8" in ct
```
```typescript
// frontend/tests/charset.test.ts
import { readFileSync } from "node:fs";
import { it, expect } from "vitest";

it("index.html declares UTF-8 first in head", () => {
  const html = readFileSync("index.html", "utf8");
  const head = html.slice(0, 1024).toLowerCase();
  expect(head).toMatch(/<meta charset="utf-8"\s*\/?>/);
  expect(html.toLowerCase().match(/charset=/g)?.length ?? 0).toBeLessThanOrEqual(1);
});
```

**Implementation Guidance:**
- Add both tests (backend pytest and frontend vitest); they verify the control from T44.
- Post-deploy: `curl -sI https://<web>/ https://<web>/patients` and a report export from the API; all must show `charset=utf-8` (or JSON).
- The test fails if any sampled page lacks a charset in both header and meta, or if pages use different charsets.
- Reference: SD Elements guidance for T132.

**Success Criteria:**
- [ ] pytest and vitest charset tests pass.
- [ ] Sampled deployed pages and exports all declare UTF-8.

**Status:** Pending
