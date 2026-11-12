---
name: t300-test-that-temporary-files-are-cleaned-up-after-the
description: Tests that ACME Clinical report generation leaves no temporary files in /tmp after success, failure or concurrent use by different users, and that the expiry sweep removes stale report directories.
---

# T300: Test that temporary files are cleaned up after the resource is used

**Category:** CODE_FIX
**SD Elements:** [T300](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T300/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "A geração das leituras, os alarmes e os relatórios devem ser feitos em Python."
> (EN: Reading generation, alarms and reports must be done in Python.)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
Reports are checked only for correct content. Leftover temp files with patient data and `/tmp` exhaustion on warm Vercel instances go undetected.

**Secure Implementation Pattern:**
```python
# backend/tests/test_temp_cleanup.py
import os, time, pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.services import reports

@pytest.fixture(autouse=True)
def isolated_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "TMP_ROOT", tmp_path / "acme-reports")
    return tmp_path / "acme-reports"

@pytest.mark.asyncio
@pytest.mark.parametrize("token_fixture", ["nurse_token", "physician_token", "admin_token"])
async def test_report_leaves_no_temp_files(token_fixture, request, isolated_tmp, patient_id):
    token = request.getfixturevalue(token_fixture)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        for _ in range(20):                                  # many files -> availability check
            r = await c.get(f"/reports/patients/{patient_id}/vitals.pdf",
                            headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200
    assert not any(isolated_tmp.iterdir())

@pytest.mark.asyncio
async def test_failed_render_cleans_up(monkeypatch, isolated_tmp):
    def boom(path): open(path, "wb").write(b"partial"); raise RuntimeError
    with pytest.raises(RuntimeError):
        reports.report_response("user-1234", boom)
    assert not any(isolated_tmp.iterdir())

def test_expired_dirs_swept(isolated_tmp):
    old = isolated_tmp / "uold-abc"; old.mkdir(parents=True)
    t = time.time() - reports.EXPIRY_SECONDS - 5; os.utime(old, (t, t))
    reports.sweep_expired()
    assert not old.exists()
```

**Implementation Guidance:**
- Run report generation as each role, then inspect the app temp root (`/tmp/acme-reports` on Vercel, isolated `tmp_path` in tests).
- Test success, render failure, and client disconnect paths; expect zero leftover files.
- Test expiry enforcement by back-dating directory mtimes.
- Identify high-volume temp producers (bulk ward reports) and test repeated calls for `/tmp` growth.
- Manual check: on a preview deployment, call a report endpoint, then an internal admin-only diagnostic (disabled in production) or Vercel Sandbox to confirm `/tmp` is clean — or rely on in-memory generation and assert no `tempfile` usage.
- Reference: SD Elements guidance for T300.

**Success Criteria:**
- [ ] `backend/tests/test_temp_cleanup.py` passes.
- [ ] 20 consecutive reports leave the temp root empty.
- [ ] Expired directories are removed by the sweep.

**Status:** Pending
