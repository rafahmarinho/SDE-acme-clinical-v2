---
name: t39-refuse-carriage-returns-and-line-feeds-when-adding
description: Prevents HTTP response splitting in the ACME Clinical FastAPI backend by refusing CR/LF in any user-influenced response header, such as report download filenames, redirect locations and cookies.
---

# T39: Refuse carriage returns and line feeds when adding data to HTTP response headers

**Category:** CODE_FIX
**SD Elements:** [T39](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T39/)
**Priority:** 4/10 · **Phase:** development

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: "frontend. The generation of readings, alarms and reports must be done in Python. The")
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
Report downloads will likely set `Content-Disposition: attachment; filename="{patient_name}-{date}.pdf"` from patient names or user-supplied report titles, and any redirect or cookie built from input would put raw values in headers. A `\r\n` in a name could inject headers or split the response.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py (helpers)
import re
from urllib.parse import quote, unquote

_CTRL = re.compile(r"[\x00-\x1f\x7f]")

def safe_header_value(value: str) -> str:
    decoded = value
    for _ in range(3):                      # catch double-encoded %250A etc.
        nxt = unquote(decoded)
        if nxt == decoded:
            break
        decoded = nxt
    if _CTRL.search(decoded):
        raise ValueError("control characters not allowed in header")
    return value

def content_disposition(filename: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:80] or "report"
    return f"attachment; filename=\"{stem}\"; filename*=UTF-8''{quote(stem)}"

# backend/app/routers/reports.py
# return Response(pdf_bytes, media_type="application/pdf",
#                 headers={"Content-Disposition": content_disposition(f"{report.id}.pdf")})
```

**Implementation Guidance:**
- Identify every header built from data: `Content-Disposition` for reports in `backend/app/routers/reports.py`, `Location` for any redirect, `Set-Cookie`, custom `X-` headers.
- Prefer server-generated values (report UUID, date) over patient names or user titles in filenames.
- When input must be included, refuse CR (`%0D`), LF (`%0A`) and other control characters after repeated URL-decoding (so `%%0A0A` / `%250A` are also caught), then RFC 5987-encode.
- Use Starlette's `Response(headers=...)` / `RedirectResponse` rather than writing raw header bytes.
- Reference: SD Elements guidance for T39.

**Success Criteria:**
- [ ] Unit tests for `safe_header_value` reject `a\r\nSet-Cookie: x=1`, `%0d%0a`, `%250A` and `%%0A0A`.
- [ ] Downloading a report for a patient whose name contains `\r\n` yields a single, sanitized `Content-Disposition` header and no injected headers.

**Status:** Applied
