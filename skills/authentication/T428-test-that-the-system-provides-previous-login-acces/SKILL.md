---
name: t428-test-that-the-system-provides-previous-login-acces
description: Tests that ACME Clinical shows previous-login details and failed-attempt counts after sign-in, and notifies users of security changes to their account, verifying T427.
---

# T428: Test that the system provides previous login (access) notifications

**Category:** CODE_FIX
**SD Elements:** [T428](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T428/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A login-history feature might show only the current login, count failures from the wrong point in time, or skip notifications for MFA or role changes. These tests check each item the countermeasure requires.

**Secure Implementation Pattern:**
```python
# backend/tests/test_previous_login_notice.py
import pytest

async def test_failed_attempts_since_last_success(client_for, db, user):
    await db.insert_login_event(user.id, success=True, minutes_ago=60)
    for m in (30, 20, 10):
        await db.insert_login_event(user.id, success=False, minutes_ago=m)
    r = await client_for(user).post("/me/session-start")
    body = r.json()
    assert body["failed_since_last_login"] == 3
    assert body["previous_logins"][0]["created_at"]           # date + time
    assert {"ip", "user_agent", "country"} <= body["previous_logins"][0].keys()

async def test_counter_resets_after_success(client_for, user):
    await client_for(user).post("/me/session-start")
    assert (await client_for(user).post("/me/session-start")).json()["failed_since_last_login"] == 0

@pytest.mark.parametrize("change", ["password_changed", "email_changed",
                                    "mfa_factor_removed", "role_changed"])
async def test_security_change_notifies(trigger_change, outbox, user, change):
    await trigger_change(user, change)
    assert outbox.sent_to(user.email, template=change)          # no login required

async def test_other_users_history_not_readable(client_for, user, other_user):
    r = await client_for(user).get(f"/users/{other_user.id}/logins")
    assert r.status_code in (403, 404)
```

**Implementation Guidance:**
- Item 1: failed attempts since the last success are shown on login (test above, plus a Vitest test that the banner renders the count).
- Item 2: successful and failed counts over a period are available on the Profile screen's "Recent activity" section (for example the last 30 days).
- Item 3: security-change notifications go to the verified email immediately (Mailpit or the simulated outbox in tests).
- Item 4: location, IP and device are shown, and the number of previous logins follows the setting.
- Manual: log in from two browsers, fail once from a third, then confirm what the banner shows.
- Reference: SD Elements guidance for T428.

**Success Criteria:**
- [ ] All tests above pass in CI.
- [ ] A manual multi-browser test record shows correct dates, devices and the failed count.

**Status:** Pending
