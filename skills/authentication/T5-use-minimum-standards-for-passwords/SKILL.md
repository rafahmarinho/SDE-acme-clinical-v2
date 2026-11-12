---
name: t5-use-minimum-standards-for-passwords
description: Enforces minimum password standards (length 12-128, complexity, breached/common password rejection via Have I Been Pwned k-anonymity, context words) whenever ACME Clinical staff set or reset a Supabase Auth password.
---

# T5: Use minimum standards for passwords

**Category:** CODE_FIX
**SD Elements:** [T5](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T5/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
The password recovery flow would call `supabase.auth.updateUser({ password })` with whatever the user typed. Supabase's default minimum is 6 characters and it does not check breached passwords, so staff with access to patient vitals could pick "Password1" or a password already leaked online.

**Secure Implementation Pattern:**
```python
# backend/app/services/password_policy.py
import hashlib
import httpx

COMMON = {"password", "password1", "p@ssw0rd", "qwerty123", "123456789012", "welcome123"}

async def is_pwned(password: str) -> bool:
    """HIBP range API (k-anonymity): only the first 5 SHA-1 hex chars leave the server."""
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # nosec - HIBP protocol, not storage
    prefix, suffix = digest[:5], digest[5:]
    async with httpx.AsyncClient(timeout=3.0) as client:
        r = await client.get(f"https://api.pwnedpasswords.com/range/{prefix}",
                             headers={"Add-Padding": "true"})
        r.raise_for_status()
    return any(line.split(":")[0] == suffix for line in r.text.splitlines())

def is_repetitive_or_sequential(pw: str) -> bool:
    if len(set(pw)) <= 2:
        return True
    seqs = "abcdefghijklmnopqrstuvwxyz0123456789"
    return any(seqs[i:i + 6] in pw.lower() for i in range(len(seqs) - 5))

async def assert_meets_minimum(pw: str, context: list[str]) -> None:
    errs = violations(pw, await load_policy(), context)      # see T4
    if pw.lower() in COMMON or is_repetitive_or_sequential(pw):
        errs.append("Password is too common or predictable.")
    if await is_pwned(pw):
        errs.append("This password appeared in a data breach. Choose another.")
    if errs:
        raise PasswordPolicyError(errs)  # mapped to 422 in backend/app/core/errors.py
```

**Implementation Guidance:**
- Baseline: at least 12 and at most 128 characters, mixed character classes, no common, dictionary, repetitive or sequential values, no context words, and no breached passwords.
- Call `assert_meets_minimum()` in every backend path that sets a password: first-login password set for invited staff, profile password change (T3), and completion of password recovery. If the HIBP check fails because of a network error, record the failure and fall back to the local common-password list. Do not block login.
- Enable Supabase "Leaked password protection" (hosted Auth settings) and set `minimum_password_length = 12` and `password_requirements` in `supabase/config.toml`, so GoTrue enforces the floor even when the backend is bypassed.
- In the frontend (`frontend/src/screens/` reset and profile screens), show the rules and a live strength hint. The backend stays authoritative.
- Never log candidate passwords. Only the 5-character SHA-1 prefix is sent to HIBP.
- Reference: SD Elements guidance for T5.

**Success Criteria:**
- [ ] Setting "Password123!" or "aaaaaaaaaaaa" through the backend returns 422 with a readable message.
- [ ] `backend/tests/test_password_minimums.py` mocks the HIBP range response (respx) and checks that a breached password is rejected and a strong random passphrase is accepted.
- [ ] Supabase config shows a minimum length of 12 or more and leaked-password protection is enabled (documented in the README).

**Status:** Pending
