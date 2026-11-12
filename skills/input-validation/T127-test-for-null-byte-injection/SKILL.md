---
name: t127-test-for-null-byte-injection
description: Test recipe ensuring ACME Clinical file uploads/downloads (Supabase Storage paths, report filenames) and text inputs reject null bytes so file-type restrictions cannot be bypassed.
---

# T127: Test for null byte injection

**Category:** CODE_FIX
**SD Elements:** [T127](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T127/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> "senha, arquivos e atualizações em tempo real."
> (EN: "Use current, stable technology versions and Supabase for PostgreSQL, email and password login, files and real-time updates.")
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
File features (attachments, maintenance documents, generated reports in Supabase Storage) will accept filenames and object paths from the client, often checking only the extension. A name like `../../config.py%00.pdf` can pass an `endswith(".pdf")` check; PostgreSQL also rejects `\x00` in text, producing 500 errors if not validated.

**Secure Implementation Pattern:**
```python
# backend/tests/test_null_byte.py
import pytest

NULLS = ["report%00.pdf", "../../etc/passwd%00.pdf", "a\x00.pdf", "note\u0000text"]

@pytest.mark.asyncio
@pytest.mark.parametrize("name", NULLS)
async def test_upload_rejects_null(client, tech_headers, name):
    r = await client.post("/api/devices/attachments",
                          files={"file": (name, b"%PDF-1.7", "application/pdf")},
                          headers=tech_headers)
    assert r.status_code in (400, 422)

@pytest.mark.asyncio
async def test_report_download_null(client, physician_headers):
    r = await client.get("/api/reports/download", params={"name": "x%00.pdf"},
                         headers=physician_headers)
    assert r.status_code in (400, 404, 422)

@pytest.mark.asyncio
async def test_text_field_null(client, nurse_headers, patient_id):
    r = await client.post(f"/api/patients/{patient_id}/observations",
                          json={"text": "ok\u0000DROP"}, headers=nurse_headers)
    assert r.status_code == 422          # never 500
```

**Implementation Guidance:**
- Locate all inputs reaching file operations: upload filenames, Storage object keys, report download identifiers.
- Append `%00` / `\0` plus an allowed extension and verify the request is refused rather than resolving a different file.
- The control under test: server-generated Storage keys (`{uuid}.{ext}` chosen from MIME sniffing), a shared validator rejecting `\x00` in all string fields (see T34), and lookups by report id instead of by path.
- Confirm text fields with NUL return 422, not a PostgreSQL 500.
- Reference: SD Elements guidance for T127.

**Success Criteria:**
- [ ] `backend/tests/test_null_byte.py` passes for upload, download and free-text endpoints.
- [ ] No endpoint returns 500 for a NUL-containing input.
- [ ] Storage object names never contain client-supplied path segments.

**Status:** Pending
