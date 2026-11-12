---
name: t297-verify-that-target-pathname-is-validated-before-re
description: Tests that ACME Clinical file and report endpoints reject path traversal, absolute paths and encoded traversal payloads, and that users cannot reach another patient's Supabase Storage objects or server files.
---

# T297: Verify that target pathname is validated before retrieving local resources

**Category:** CODE_FIX
**SD Elements:** [T297](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T297/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
File download and report template selection are tested only with valid names. Traversal (`../`), absolute and encoded paths, or object keys of other patients are never tried.

**Secure Implementation Pattern:**
```python
# backend/tests/test_path_traversal.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.services.reports import template_path

PAYLOADS = ["../MYFILE.TXT", "..../MYFILE.TXT", "../..../MYFILE.TXT", "/etc/passwd",
            "c:\\windows\\win.ini", "%2e%2e/MYFILE.TXT", "%2e%2e%2fMYFILE.TXT",
            "%252E%252E%252FMYFILE.TXT", "patients/other-id/scan.png", "ward_summary\x00.html"]

@pytest.mark.parametrize("p", PAYLOADS)
def test_template_path_rejects(p):
    with pytest.raises(ValueError):
        template_path(p)

@pytest.mark.asyncio
@pytest.mark.parametrize("p", PAYLOADS)
async def test_file_endpoints_reject(p, nurse_token):
    h = {"Authorization": f"Bearer {nurse_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r1 = await c.get(f"/files/{p}/url", headers=h)
        r2 = await c.get("/reports/generate", params={"template": p}, headers=h)
    assert r1.status_code in (404, 422) and r2.status_code == 422

@pytest.mark.asyncio
async def test_cannot_get_other_ward_file(nurse_token, other_ward_file_id):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/files/{other_ward_file_id}/url", headers={"Authorization": f"Bearer {nurse_token}"})
    assert r.status_code == 404

def test_double_dot_filename_handled():
    with pytest.raises(ValueError):       # not in allow-list; must not crash
        template_path("MYFILE..TXT")
```

**Implementation Guidance:**
- Locate every place a file/resource location is computed: Storage signed URL route, upload route, report template/asset loading in `services/reports.py`.
- Run the payload list against each; expect 404/422 and no content of files outside the app workspace.
- Test Storage directly: with a nurse's Supabase JWT, try `storage.from_('patient-files').download('<other patient prefix>/...')` and `list('')`; expect denial by storage RLS.
- Note: `MYFILE..TXT` must be handled gracefully (no 500).
- Reference: SD Elements guidance for T297.

**Success Criteria:**
- [ ] All traversal payloads rejected by API and helpers.
- [ ] Cross-patient Storage access denied via API and direct Storage client.
- [ ] No 500 responses for any payload.

**Status:** Pending
