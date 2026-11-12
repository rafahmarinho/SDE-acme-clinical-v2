---
name: t81-test-account-lockout
description: Security test verifying that five consecutive failed Supabase email/password logins to an ACME Clinical account trigger a temporary lockout or anti-automation control (CAPTCHA, rate limit), verifying T6.
---

# T81: Test account lockout

**Category:** CODE_FIX
**SD Elements:** [T81](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T81/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e senha"
> (EN: Use current, stable technologies and Supabase for PostgreSQL, email and password login)
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
If the password-verification hook is not registered in the hosted project, or CAPTCHA is turned off for demo convenience, login works but brute force goes unchecked. Only a test can show that the lockout from T6 is actually active.

**Secure Implementation Pattern:**
```python
# backend/tests/integration/test_account_lockout.py  (runs against `supabase start`)
import os
import httpx
import pytest

URL = os.environ["SUPABASE_URL"]
ANON = os.environ["SUPABASE_ANON_KEY"]
EMAIL, GOOD = os.environ["LOCKOUT_TEST_EMAIL"], os.environ["LOCKOUT_TEST_PASSWORD"]

def login(pw: str) -> httpx.Response:
    return httpx.post(f"{URL}/auth/v1/token?grant_type=password",
                      headers={"apikey": ANON}, json={"email": EMAIL, "password": pw})

@pytest.mark.integration
def test_lockout_after_five_failures():
    for _ in range(5):
        assert login("definitely-wrong").status_code in (400, 429)
    r = login(GOOD)                         # correct password on 6th try
    assert r.status_code in (400, 429), "account not temporarily locked"
    assert "access_token" not in r.text
```

**Implementation Guidance:**
- Create a dedicated, non-demo test user in the integration fixture through the Admin API, with a random password taken from env and never committed.
- Run with CAPTCHA disabled only in the local test config, so the test exercises the hook, and add a separate test that `config.toml` has CAPTCHA enabled for the deployed environments.
- After the test, call the admin unlock endpoint and confirm that login succeeds. Confirm that a soft-lock expiry does not clear a ban (T6).
- Manual check on the deployed Vercel frontend: five wrong passwords should show a CAPTCHA challenge or a lockout, while the message stays generic.
- Reference: SD Elements guidance for T81.

**Success Criteria:**
- [ ] The integration test passes: the 6th attempt with the correct password returns no session.
- [ ] Admin unlock restores access, and the lock event appears in the audit log.

**Status:** Pending
