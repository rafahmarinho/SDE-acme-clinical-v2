---
name: t129-test-for-reliance-on-file-name-or-extension-of-ext
description: Tests that ACME Clinical file uploads to Supabase Storage (e.g. observation attachments, maintenance documents, profile photos) reject files whose real content does not match the allowed type, regardless of extension or client Content-Type.
---

# T129: Test for reliance on file name or extension of externally-supplied file

**Category:** CODE_FIX
**SD Elements:** [T129](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T129/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
"Arquivos" via Supabase Storage is often implemented by uploading straight from the browser with the file's own name and `file.type`. The allow-list (if any) checks the `.jpg`/`.pdf` extension, so a renamed HTML or script file is accepted and later served.

**Secure Implementation Pattern:**
```python
# backend/tests/test_upload_type_spoofing.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

SPOOFED = [
    ("photo.jpg", b"<html><script>alert(1)</script></html>", "image/jpeg"),
    ("report.pdf", b"MZ\x90\x00\x03\x00\x00\x00", "application/pdf"),        # PE executable
    ("scan.png", b"GIF89a....", "image/png"),                               # wrong image type
    ("notes.txt.jpg", b"plain text pretending", "image/jpeg"),
]

@pytest.mark.asyncio
@pytest.mark.parametrize("name,content,ctype", SPOOFED)
async def test_extension_spoofing_rejected(name, content, ctype, nurse_token, patient_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/patients/{patient_id}/files",
                         files={"file": (name, content, ctype)},
                         headers={"Authorization": f"Bearer {nurse_token}"})
    assert r.status_code in (415, 422)

@pytest.mark.asyncio
async def test_valid_png_accepted(nurse_token, patient_id, tiny_png_bytes):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/patients/{patient_id}/files", files={"file": ("x.bin", tiny_png_bytes, "application/octet-stream")},
                         headers={"Authorization": f"Bearer {nurse_token}"})
    assert r.status_code == 201 and r.json()["content_type"] == "image/png"
```

**Implementation Guidance:**
- Inventory every upload point (backend upload route, and any direct `supabase.storage.from(...).upload` in `frontend/src/services`). Direct browser uploads bypass server validation — test that Storage RLS/bucket `allowed_mime_types` blocks them, or that the frontend has no direct upload path.
- For each allowed type, upload a file of another type with the allowed extension and MIME; expect 415/422 and no object created in the bucket.
- Verify the stored `content_type` is derived from detected content (T54), not from the request.
- Reference: SD Elements guidance for T129.

**Success Criteria:**
- [ ] All spoofed uploads rejected; bucket contains no new objects after the test.
- [ ] Direct Storage upload with the anon/authenticated key is denied by policy (integration test against local Supabase).
- [ ] Test runs in CI.

**Status:** Applied
