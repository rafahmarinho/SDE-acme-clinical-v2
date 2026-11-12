---
name: t1544-isolate-untrusted-content-in-a-sandbox
description: Sandboxes any untrusted content in ACME Clinical (optional third-party 3D visualization iframe, previews of uploaded files, generated report HTML) with the iframe sandbox attribute or a CSP sandbox header, never combining allow-scripts with allow-same-origin.
---

# T1544: Isolate untrusted content in a sandbox

**Category:** CODE_FIX
**SD Elements:** [T1544](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T1544/)
**Priority:** 5/10 · **Phase:** architecture-design

**Spec Context:**
> "senha, arquivos e atualizações em tempo real."
> (EN: password, files and real-time updates.)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
Files stored in Supabase Storage (attachments, report previews) and an optional 3D visualization may be rendered in an `<iframe>` without restrictions. A malicious uploaded HTML/SVG file or compromised viewer script could then run scripts, submit forms, open popups or navigate the top-level clinical app.

**Secure Implementation Pattern:**
```tsx
// frontend/src/components/FilePreview.tsx
export function FilePreview({ signedUrl, mime }: { signedUrl: string; mime: string }) {
  if (mime === "image/png" || mime === "image/jpeg") {
    return <img src={signedUrl} alt="Attachment preview" referrerPolicy="no-referrer" />;
  }
  if (mime === "text/html") {
    // legacy/generated HTML only: fully sandboxed (no scripts, forms, popups; unique origin).
    // Requires the Storage origin in CSP frame-src.
    return <iframe title="File preview" src={signedUrl} sandbox="" referrerPolicy="no-referrer" />;
  }
  // PDFs and everything else: download only (browsers' PDF viewers do not run in sandbox="")
  return <a href={signedUrl} download rel="noopener noreferrer">Download</a>;
}

// Optional third-party 3D view (cross-origin, see T1543): scripts only
<iframe title="3D ward" src={VIZ_ORIGIN} sandbox="allow-scripts" />
```
```python
# backend/app/routers/reports.py - if the API ever serves HTML report previews
from fastapi.responses import HTMLResponse

@router.get("/api/reports/{report_id}/preview", response_class=HTMLResponse)
async def preview(report_id: str, user=Depends(current_user)):
    html = await render_report_html(report_id, user)
    return HTMLResponse(html, headers={"Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'"})
```

**Implementation Guidance:**
- Use `sandbox=""` (all restrictions) for previews of stored files in `frontend/src/components`; only add flags that are strictly needed.
- Never combine `allow-scripts` with `allow-same-origin`; together they let the frame remove its own sandbox.
- For the optional third-party 3D iframe use `sandbox="allow-scripts"` only (no `allow-top-navigation`, `allow-popups`, `allow-forms`).
- Restrict uploadable types (PDF, PNG, JPEG, CSV) in the backend upload path and in Supabase Storage bucket `allowed_mime_types`; reject HTML/SVG uploads.
- Any HTML the server returns for untrusted/generated content gets `Content-Security-Policy: sandbox`.
- Reference: SD Elements guidance for T1544.

**Success Criteria:**
- [ ] Every `<iframe>` in `frontend/src` has a `sandbox` attribute; none include both `allow-scripts` and `allow-same-origin` (enforce with a grep/ESLint check).
- [ ] Uploading an HTML or SVG file is rejected; a test under `backend/tests` covers this.
- [ ] A test file with `<script>top.location='https://example.org'</script>` cannot navigate the app when previewed.

**Status:** Pending
