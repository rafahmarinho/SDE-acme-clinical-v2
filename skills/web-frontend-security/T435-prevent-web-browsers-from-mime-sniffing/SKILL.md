---
name: t435-prevent-web-browsers-from-mime-sniffing
description: Sends X-Content-Type-Options nosniff and correct Content-Type headers from both ACME Clinical Vercel deployments (React SPA and FastAPI API) and for Supabase Storage uploads, so browsers never reinterpret JSON, reports or uploaded files as executable content.
---

# T435: Prevent web browsers from MIME sniffing

**Category:** CODE_FIX
**SD Elements:** [T435](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T435/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "senha, arquivos e atualizações em tempo real."
> (EN: password, files and real-time updates.)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
Files (reports, attachments) are stored in Supabase Storage and the API returns JSON and generated reports. Without `nosniff` and an explicit content type, a browser may sniff an uploaded file or a JSON response containing attacker-controlled text (e.g. an observation) as HTML/script and execute it.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py (part of the security headers middleware)
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        ct = response.headers.get("content-type")
        if ct and ct.startswith(("application/json", "text/")) and "charset" not in ct:
            response.headers["content-type"] = f"{ct}; charset=utf-8"
        return response

# backend/app/services/reports.py - explicit type on upload
supabase.storage.from_("reports").upload(
    path, pdf_bytes,
    {"content-type": "application/pdf", "cache-control": "no-store", "upsert": "false"},
)
```

```json
{ "headers": [ { "source": "/(.*)", "headers": [
  { "key": "X-Content-Type-Options", "value": "nosniff" } ] } ] }
```

**Implementation Guidance:**
- Add `SecurityHeadersMiddleware` in `backend/app/core/security.py` and register it in `backend/app/main.py`.
- Add the `X-Content-Type-Options: nosniff` rule to `frontend/vercel.json` `headers` for all paths.
- Always return typed responses from FastAPI (`JSONResponse`, `Response(media_type=...)`); never return user-controlled bytes without `media_type`.
- On Supabase Storage uploads, set `content-type` server-side from an allow-list (`application/pdf`, `text/csv`, `image/png`), not from the client filename; serve downloads with `Content-Disposition: attachment`.
- Reference: SD Elements guidance for T435.

**Success Criteria:**
- [ ] Every API and frontend response includes `X-Content-Type-Options: nosniff`.
- [ ] Stored report objects have an explicit allow-listed content type.
- [ ] Verified by T436 tests.

**Status:** Pending
