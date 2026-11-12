---
name: t572-check-for-symlinks-before-opening-files
description: Ensures that ACME Clinical's only local file operations, the temporary files used by Python report generation in Vercel's /tmp, are created with tempfile in a private directory and opened with O_NOFOLLOW so symlinks or hard links cannot redirect reads or writes.
---

# T572: Check for symlinks before opening files

**Category:** CODE_FIX
**SD Elements:** [T572](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T572/)
**Priority:** 6/10 · **Phase:** development

**Spec Context:**
> "A geração das leituras, os alarmes e os relatórios devem ser feitos em Python."
> (EN: Reading generation, alarms and reports must be done in Python.)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
User files live in Supabase Storage (object storage, no symlinks), so the relevant local file I/O is report generation: e.g. writing `/tmp/report_<patient>.pdf` with a predictable name before uploading it. On a shared or warm Vercel instance (or local dev host), a pre-placed symlink at that path could redirect the write or feed attacker-controlled input to the report.

**Secure Implementation Pattern:**
```python
# backend/app/services/reports.py
import os, stat, tempfile
from contextlib import contextmanager

@contextmanager
def private_workdir():
    # mkdtemp: random name, mode 0700, created atomically (no pre-existing link)
    with tempfile.TemporaryDirectory(prefix="acme-report-", dir="/tmp") as d:
        yield d

def open_no_follow(path: str, flags: int = os.O_RDONLY):
    fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0))
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:   # reject devices, FIFOs, hard links
        os.close(fd)
        raise PermissionError("unexpected file type")
    return os.fdopen(fd, "rb" if flags == os.O_RDONLY else "wb")

def create_exclusive(dirpath: str, name: str):
    # O_EXCL + O_NOFOLLOW: fails if anything (including a symlink) already exists
    fd = os.open(os.path.join(dirpath, name),
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    return os.fdopen(fd, "wb")
```

**Implementation Guidance:**
- Relevance: Supabase Storage objects cannot be symlinks; this CM applies to local temp files in report generation (`services/reports.py`) and any local dev scripts (seed/import). Vercel's filesystem is read-only except `/tmp`, which may be reused across warm invocations.
- Never build temp paths from patient IDs, report names or other user input; use `tempfile.TemporaryDirectory`/`NamedTemporaryFile` which create files atomically with `O_EXCL` and 0600 permissions.
- When re-opening a file you created, use `O_NOFOLLOW` and `fstat` checks (regular file, `st_nlink == 1`); prefer keeping the file descriptor open rather than re-opening by path.
- Prefer in-memory generation (`io.BytesIO`) when report size allows, avoiding the filesystem entirely.
- Static assets used by reports (fonts, logos) are read only from the deployed package path resolved at start-up, never from `/tmp`.
- Reference: SD Elements guidance for T572.

**Success Criteria:**
- [ ] No `open()` on paths under `/tmp` built from string concatenation; all temp files via `tempfile` helpers.
- [ ] Unit test: `open_no_follow` raises on a symlink and on a hard-linked file (see T595).
- [ ] Report generation works with in-memory buffers or private temp dirs only.

**Status:** Pending
