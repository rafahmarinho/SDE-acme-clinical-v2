---
name: t595-test-that-your-application-checks-for-symlinks-bef
description: Pytest checks that ACME Clinical's report temp-file helpers refuse to read or write through symlinks or hard links planted in /tmp or the report work directory.
---

# T595: Test that your application checks for symlinks before opening files

**Category:** CODE_FIX
**SD Elements:** [T595](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T595/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "A geração das leituras, os alarmes e os relatórios devem ser feitos em Python."
> (EN: Reading generation, alarms and reports must be done in Python.)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
Report generation in Python is the only place that opens local files (temp files in Vercel `/tmp`). Without a test, a regression to `open("/tmp/report.pdf", "wb")` would silently follow a planted symlink.

**Secure Implementation Pattern:**
```python
# backend/tests/test_symlink_protection.py
import os, sys, pytest
from app.services.reports import open_no_follow, create_exclusive, private_workdir

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX link semantics")

def test_read_through_symlink_rejected(tmp_path):
    secret = tmp_path / "outside.txt"; secret.write_text("secret")
    link = tmp_path / "report.csv"; link.symlink_to(secret)
    with pytest.raises(OSError):
        open_no_follow(str(link))

def test_hard_link_rejected(tmp_path):
    target = tmp_path / "t.txt"; target.write_text("x")
    hl = tmp_path / "h.txt"; os.link(target, hl)
    with pytest.raises(PermissionError):
        open_no_follow(str(hl))

def test_exclusive_create_does_not_follow_preplaced_link(tmp_path):
    victim = tmp_path / "victim.txt"; victim.write_text("keep")
    (tmp_path / "out.pdf").symlink_to(victim)
    with pytest.raises(FileExistsError):
        create_exclusive(str(tmp_path), "out.pdf")
    assert victim.read_text() == "keep"

def test_workdir_is_private():
    with private_workdir() as d:
        assert not os.path.islink(d) and (os.stat(d).st_mode & 0o077) == 0
```

**Implementation Guidance:**
- Identify every local file open: report generation (`services/reports.py`), any CSV/PDF export, local seed/import scripts.
- For each, plant a symlink (and a hard link) at the expected path pointing outside the app realm; assert the operation fails and the target is untouched.
- Run in CI on Linux (Vercel's Python runtime is Linux); skip on Windows dev machines.
- Also run a static check (grep/semgrep) that no `open(` targets `/tmp` paths outside these helpers.
- Reference: SD Elements guidance for T595.

**Success Criteria:**
- [ ] All tests in `backend/tests/test_symlink_protection.py` pass on Linux CI.
- [ ] Planted link targets remain unmodified.
- [ ] Semgrep/grep rule for raw `/tmp` opens added to CI.

**Status:** Applied
