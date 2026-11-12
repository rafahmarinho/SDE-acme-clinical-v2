---
name: t1469-prevent-sensitive-data-leakage-through-content-sec
description: Hosts the ACME Clinical CSP violation reporting endpoint in the FastAPI API (not a generic third-party logger), validates and size-limits reports, strips URL paths and query strings that could contain patient identifiers, and stores sanitized reports with restricted access.
---

# T1469: Prevent sensitive data leakage through Content Security Policy (CSP) reports

**Category:** CODE_FIX
**SD Elements:** [T1469](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1469/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
Following T331, a developer might point `report-uri` at a free third-party CSP collector. Browser reports include `document-uri`, `referrer` and `blocked-uri`, which for patient detail routes (e.g. `/patients/<id>`) and Supabase signed Storage URLs (with tokens in the query string) would leak patient identifiers and access tokens to an outside party.

**Secure Implementation Pattern:**
```python
# backend/app/routers/csp.py
from urllib.parse import urlsplit
from fastapi import APIRouter, Request, Response
from app.core.logging import security_logger

router = APIRouter()
MAX_BYTES = 8 * 1024
FIELDS = ("document-uri", "referrer", "blocked-uri", "violated-directive",
          "effective-directive", "disposition", "status-code")

def _redact(url: str | None) -> str | None:
    if not url or "://" not in url:
        return url  # keywords like 'inline', 'eval'
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"  # drop path, query, fragment (ids, tokens)

@router.post("/api/csp-report", status_code=204)
async def csp_report(request: Request) -> Response:
    body = await request.body()
    if len(body) > MAX_BYTES or request.headers.get("content-type", "").split(";")[0] not in {
        "application/csp-report", "application/reports+json", "application/json"}:
        return Response(status_code=204)  # drop silently
    import json
    try:
        data = json.loads(body)
    except ValueError:
        return Response(status_code=204)
    reports = data if isinstance(data, list) else [data.get("csp-report", {})]
    for rep in reports[:10]:
        rep = rep.get("body", rep)
        clean = {k: rep.get(k) for k in FIELDS}
        for k in ("document-uri", "referrer", "blocked-uri"):
            clean[k] = _redact(clean[k])
        security_logger.warning("csp_violation", extra={"report": clean})
    return Response(status_code=204)
```

**Implementation Guidance:**
- Host the endpoint ourselves in the FastAPI deployment (`backend/app/routers/csp.py`, registered in `backend/app/main.py`); it is unauthenticated by nature, so rate-limit it and never echo input.
- Redact paths/queries before logging: patient detail routes and signed Storage URLs carry identifiers/tokens. Also prefer route designs that keep identifiers out of URLs (see T219).
- Log through `backend/app/core/logging.py` (structured JSON, no PHI); if persisted, use a Supabase table with RLS allowing only `administrator` reads, plus a retention job that deletes reports older than 30 days.
- If a third-party collector is ever used, choose one with a signed DPA/BAA and deletion support, and still send only redacted data.
- Exclude `/api/csp-report` from CORS credentialed access; browsers send reports without credentials.
- Reference: SD Elements guidance for T1469.

**Success Criteria:**
- [ ] `report-uri`/`report-to` in `frontend/vercel.json` points only to the ACME Clinical API.
- [ ] `backend/tests/test_csp_report.py` posts a report with `document-uri: https://web/patients/123?token=abc` and asserts the logged record contains only the origin.
- [ ] Oversized or malformed reports are dropped with 204.

**Status:** Pending
