---
name: t54-validate-file-contents
description: Validates ACME Clinical uploads by magic bytes and full decoding (Pillow for images, pypdf for PDFs) with size limits in the FastAPI backend before storing them in Supabase Storage, ignoring client file extension and Content-Type.
---

# T54: Validate file contents

**Category:** CODE_FIX
**SD Elements:** [T54](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T54/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

> "Use Python com FastAPI e Pydantic no backend e"
> (EN: Use Python with FastAPI and Pydantic in the backend and)
> Source: specs/PRD.md, line 17

**What the spec implies (naive approach):**
Validation by `UploadFile.filename.endswith(".jpg")` or `UploadFile.content_type`, both attacker-controlled. Polyglot or disguised files reach Storage and other clinicians' browsers.

**Secure Implementation Pattern:**
```python
# backend/app/services/files.py
import io
from fastapi import HTTPException, UploadFile
from PIL import Image
from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
MAGIC = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg", b"%PDF-": "application/pdf"}
Image.MAX_IMAGE_PIXELS = 40_000_000            # decompression-bomb guard

async def read_and_validate(file: UploadFile) -> tuple[bytes, str]:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large.")
    mime = next((m for sig, m in MAGIC.items() if data.startswith(sig)), None)
    if mime is None:
        raise HTTPException(415, "Unsupported file type.")
    try:
        if mime.startswith("image/"):
            with Image.open(io.BytesIO(data)) as img:
                img.verify()                     # full structural check
                if Image.MIME.get(img.format) != mime:
                    raise ValueError
        else:
            if b"/JavaScript" in data or b"/JS" in data or b"/Launch" in data:
                raise ValueError                 # active content not allowed
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ValueError
            _ = len(reader.pages)
    except Exception:
        raise HTTPException(422, "File content is invalid.")
    return data, mime                            # caller stores `mime` as content_type
```

**Implementation Guidance:**
- Implement in `backend/app/services/files.py`; in the upload router, read with the size cap, run the malware scan (T53) on the raw bytes (so detections are logged even for malformed files), then this content validation, then storage (T2167).
- Detect type from magic bytes, then fully parse with a format library (Pillow `verify()`; pypdf) — magic bytes alone are insufficient for polyglots. Consider re-encoding images (strip metadata/EXIF) before storing.
- Enforce size limit while reading (do not trust `Content-Length`); Vercel also caps request bodies (~4.5 MB) — set `MAX_BYTES` accordingly or use signed upload URLs to a quarantine bucket plus backend validation.
- Store the detected MIME as the Storage `content-type` and serve downloads with `Content-Disposition: attachment` for PDFs.
- Reject PDFs with embedded JavaScript/encryption.
- Reference: SD Elements guidance for T54.

**Success Criteria:**
- [ ] Upload route uses `read_and_validate`; extension/Content-Type are ignored.
- [ ] Unit tests: truncated PNG, HTML renamed `.jpg`, PDF with `/JavaScript`, oversized file all rejected.
- [ ] T129 spoofing test passes.

**Status:** Applied
