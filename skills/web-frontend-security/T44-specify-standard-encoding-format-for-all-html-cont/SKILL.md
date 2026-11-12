---
name: t44-specify-standard-encoding-format-for-all-html-cont
description: Declares UTF-8 consistently for all ACME Clinical HTML, JSON, CSV and report responses (Vite index.html meta charset, Content-Type charset in vercel.json and FastAPI) to prevent charset-confusion XSS and garbled patient data.
---

# T44: Specify standard encoding format for all HTML content

**Category:** CODE_FIX
**SD Elements:** [T44](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T44/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "Use inglês como idioma padrão em todas as telas, mensagens, relatórios e dados de exemplo."
> (EN: Use English as the default language on all screens, messages, reports and sample data.)
> Source: specs/PRD.md, line 3

**What the spec implies (naive approach):**
Even with English UI, patient names and observations may contain non-ASCII characters. If responses or generated reports (CSV/HTML) omit a charset, browsers guess the encoding; inconsistent or guessed charsets (e.g. UTF-7) enable filter bypass/XSS and corrupt data.

**Secure Implementation Pattern:**
```html
<!-- frontend/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ACME Clinical</title>
  </head>
  <body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```
```json
{ "headers": [{ "source": "/((?!assets/).*)", "headers": [
  { "key": "Content-Type", "value": "text/html; charset=utf-8" } ] }] }
```
```python
# backend/app/services/reports.py - CSV/HTML exports
from fastapi.responses import Response
def csv_response(body: str, filename: str) -> Response:
    return Response(body.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

**Implementation Guidance:**
- Keep `<meta charset="UTF-8">` as the first element in `<head>` of `frontend/index.html` (within the first 1024 bytes).
- Vercel serves `.html` as `text/html; charset=utf-8` by default; only add an explicit Content-Type rule if a rewrite changes it, and verify after deploy.
- FastAPI `JSONResponse` is UTF-8 by spec; for `text/*` responses (CSV, HTML previews, plain text) always set `; charset=utf-8` (the security headers middleware in T435 can append it).
- Write report files to Supabase Storage with `content-type: text/csv; charset=utf-8` and encode bytes as UTF-8.
- Reference: SD Elements guidance for T44.

**Success Criteria:**
- [ ] All HTML and text responses from both deployments declare UTF-8, and no page declares a different charset.
- [ ] Verified by T132 tests.

**Status:** Pending
