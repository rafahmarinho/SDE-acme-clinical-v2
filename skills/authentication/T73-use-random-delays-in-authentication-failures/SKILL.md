---
name: t73-use-random-delays-in-authentication-failures
description: Adds a constant-floor-plus-random-jitter delay to ACME Clinical's backend-owned authentication failure paths (current-password check, staff invite, internal service auth) so response timing does not reveal why authentication failed.
---

# T73: Use random delays in authentication failures

**Category:** CODE_FIX
**SD Elements:** [T73](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T73/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Backend endpoints such as change password, staff invitation and the internal simulation trigger would return as soon as they reach the first failing check, for example "user not found" before any password hashing. The response time then shows which branch failed and whether an account exists.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
import asyncio
import secrets
import time
from contextlib import asynccontextmanager

FLOOR_S = 0.40          # longer than the slowest legitimate path (bcrypt + GoTrue round trip)
JITTER_MS = 250

@asynccontextmanager
async def uniform_auth_timing():
    """Every exit (success or failure) takes at least FLOOR_S plus random jitter."""
    start = time.monotonic()
    try:
        yield
    finally:
        target = FLOOR_S + secrets.randbelow(JITTER_MS) / 1000
        remaining = target - (time.monotonic() - start)
        if remaining > 0:
            await asyncio.sleep(remaining)

# usage in backend/app/routers/profile.py
async def change_password(...):
    async with uniform_auth_timing():
        ...  # verify current password, raise HTTPException on failure
```

**Implementation Guidance:**
- Wrap every backend handler that checks a credential or identity in `uniform_auth_timing()`: `POST /me/password`, staff invite and resend (`backend/app/routers/` team router), and internal service-secret checks (T10). The floor must exceed the slowest real path, and the jitter comes from `secrets`, not `random`.
- Use `asyncio.sleep`, never `time.sleep`, so the Vercel Python function does not block other requests.
- The login request itself goes from the browser to Supabase GoTrue. App code cannot add a delay there, so verify GoTrue's timing with the T124 test, and rely on CAPTCHA and the lockout hook (T6) to limit sampling.
- Compare secrets with `hmac.compare_digest`.
- Reference: SD Elements guidance for T73.

**Success Criteria:**
- [ ] For each wrapped endpoint, the mean latency difference between failure modes (unknown user, wrong password, success) is under the jitter range over 50 samples.
- [ ] `backend/tests/test_auth_timing.py` checks that a failing call takes at least `FLOOR_S` and that delays vary between calls.

**Status:** Pending
