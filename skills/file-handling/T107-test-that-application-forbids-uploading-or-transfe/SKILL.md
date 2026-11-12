---
name: t107-test-that-application-forbids-uploading-or-transfe
description: Tests that ACME Clinical rejects the EICAR anti-malware test file on every upload path (backend upload route and any direct Supabase Storage access) and logs the detection.
---

# T107: Test that application forbids uploading or transferring malware

**Category:** CODE_FIX
**SD Elements:** [T107](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T107/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
Upload is tested only with normal images/PDFs. Malware acceptance would be discovered only after an incident.

**Secure Implementation Pattern:**
```python
# backend/tests/test_malware_upload.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
PNG_WITH_EICAR = b"\x89PNG\r\n\x1a\n" + EICAR          # passes magic check, must fail scan

@pytest.mark.asyncio
@pytest.mark.parametrize("name,data,ctype,expect_scan_event", [
    ("eicar.png", PNG_WITH_EICAR, "image/png", True),
    ("eicar.com", EICAR, "application/octet-stream", False),   # blocked earlier by type policy
])
async def test_eicar_rejected(name, data, ctype, expect_scan_event, physician_token,
                              patient_id, storage_objects, caplog):
    before = storage_objects()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post(f"/patients/{patient_id}/files", files={"file": (name, data, ctype)},
                         headers={"Authorization": f"Bearer {physician_token}"})
    assert r.status_code in (415, 422)
    assert storage_objects() == before                       # nothing persisted
    if expect_scan_event:
        assert any("upload_malware_detected" in m for m in caplog.messages)

def test_direct_storage_upload_blocked(supabase_as_nurse):
    with pytest.raises(Exception):
        supabase_as_nurse.storage.from_("patient-files").upload(
            "any/eicar.pdf", PDF_WITH_EICAR, {"content-type": "application/pdf"})
```

**Implementation Guidance:**
- Keep the EICAR string in the test file only (it is benign); some local AV may quarantine it — store it split/concatenated if needed.
- Test every upload path: backend route, and confirm direct client uploads to Storage are denied by RLS (T2167) so the scan cannot be bypassed.
- If any remote transfer exists (e.g. simulated device import), send the same payload there.
- Assert the file is not in the bucket/quarantine-cleared list and a security event is logged.
- Reference: SD Elements guidance for T107.

**Success Criteria:**
- [ ] EICAR upload fails on every path and leaves no stored object.
- [ ] Detection event recorded in `acme.security` / `security_events`.
- [ ] Test runs in CI.

**Status:** Applied
