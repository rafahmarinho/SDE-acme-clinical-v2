---
name: t157-temporary-files-must-be-cleaned-up-after-the-resou
description: Ensures temporary files created by ACME Clinical's Python report generation in Vercel's ephemeral /tmp are created per request in private tempfile directories, deleted immediately after upload or streaming, and swept by an expiry check, so patient report data does not persist on warm instances.
---

# T157: Temporary files must be cleaned up after the resource is used

**Category:** CODE_FIX
**SD Elements:** [T157](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T157/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "A geração das leituras, os alarmes e os relatórios devem ser feitos em Python."
> (EN: Reading generation, alarms and reports must be done in Python.)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
PDF/CSV reports written to `/tmp/report.pdf` and returned with `FileResponse`, never deleted. On a warm Vercel instance the next request (possibly by another user) can find leftover patient data, and `/tmp` fills up (512 MB limit), breaking the function.

**Secure Implementation Pattern:**
```python
# backend/app/services/reports.py
import os, shutil, tempfile, time
from pathlib import Path
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse

TMP_ROOT = Path(tempfile.gettempdir()) / "acme-reports"          # /tmp on Vercel
EXPIRY_SECONDS = 600

def sweep_expired() -> None:
    TMP_ROOT.mkdir(mode=0o700, exist_ok=True)
    now = time.time()
    for d in TMP_ROOT.iterdir():
        if not d.is_symlink() and d.is_dir() and now - d.stat().st_mtime > EXPIRY_SECONDS:
            shutil.rmtree(d, ignore_errors=True)

def report_response(user_id: str, render) -> FileResponse:
    sweep_expired()                                               # explicit watchdog check per call
    workdir = tempfile.mkdtemp(prefix=f"u{user_id[:8]}-", dir=TMP_ROOT)   # 0700, random suffix
    try:
        path = os.path.join(workdir, "report.pdf")
        render(path)
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return FileResponse(path, media_type="application/pdf", filename="report.pdf",
                        background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True))
```

**Implementation Guidance:**
- Prefer in-memory generation (`io.BytesIO` + `StreamingResponse`) so no temp file exists; use the pattern above only when a library requires a filesystem path.
- Group files per user/request (`/tmp/acme-reports/u<userid>-<random>/`) created with `tempfile.mkdtemp` (0700); never predictable names (T572).
- Delete immediately after the response is sent (`BackgroundTask`) or after uploading the report to private Storage; delete on errors too.
- Expiry policy: report temp dirs expire after 10 minutes; `sweep_expired()` runs on each report request (serverless has no long-lived watchdog thread) and can also run from a Vercel Cron endpoint.
- On logout, the frontend calls Supabase `signOut`; any server-side per-session temp data must not outlive the request anyway, so no logout dependency is needed.
- Reference: SD Elements guidance for T157.

**Success Criteria:**
- [ ] After a report download, `/tmp/acme-reports` contains no directory for that request.
- [ ] Failed report rendering leaves no temp files.
- [ ] Directories older than 10 minutes are removed by `sweep_expired` (unit test with patched mtime).

**Status:** Applied
