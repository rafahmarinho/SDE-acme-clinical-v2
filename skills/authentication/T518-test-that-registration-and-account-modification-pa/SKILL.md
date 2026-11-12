---
name: t518-test-that-registration-and-account-modification-pa
description: Tests that ACME Clinical's staff invite and email-change flows do not allow user enumeration: anti-automation after repeated requests, identical responses, owner warnings, and single-use, expiring confirmation links, verifying T517.
---

# T518: Test that registration and account modification pages are protected against user enumeration

**Category:** CODE_FIX
**SD Elements:** [T518](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T518/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Profile edits (email change) and team-management invites are where enumeration usually returns, through a specific "already exists" error or a missing owner warning. These tests make sure that does not happen.

**Secure Implementation Pattern:**
```python
# backend/tests/test_registration_enumeration.py
async def test_identical_responses(admin_client, existing_staff):
    a = await admin_client.post("/admin/staff", json=staff(existing_staff.email, "E10"))
    b = await admin_client.post("/admin/staff", json=staff("brand.new@acme.test", "E11"))
    assert (a.status_code, a.json()) == (b.status_code, b.json())

async def test_owner_warned(admin_client, existing_staff, outbox):
    await admin_client.post("/admin/staff", json=staff(existing_staff.email, "E12"))
    assert outbox.sent_to(existing_staff.email, template="account_creation_attempt")

async def test_rate_limited(admin_client):
    codes = [(await admin_client.post("/admin/staff",
              json=staff(f"u{i}@acme.test", f"E2{i}"))).status_code for i in range(12)]
    assert 429 in codes
```
```python
# backend/tests/integration/test_email_change_links.py  (local Supabase + Mailpit)
@pytest.mark.integration
def test_email_change_link_single_use_and_expiring(user_session, mailpit, freeze_otp_expiry):
    user_session.update_user({"email": "taken@acme.test"})
    link = mailpit.latest_link("taken@acme.test")
    assert http_get(link).ok and not http_get(link).ok        # second click rejected
    freeze_otp_expiry(seconds=3601)
    user_session.update_user({"email": "other@acme.test"})
    assert not http_get(mailpit.latest_link("other@acme.test")).ok
```

**Implementation Guidance:**
- Step 1: send 10 or more invite or email-change requests and expect 429 or a CAPTCHA requirement (backend limiter plus Supabase `email_sent` rate limit).
- Step 2: compare responses for existing and unique emails, for the invite API and for the Profile screen message (Vitest).
- Step 3: an existing owner receives a warning when someone tries to register their address.
- Steps 4 to 6: email change sends a validation link (both addresses, `double_confirm_changes`). The link works once and fails after `otp_expiry`. Use local Supabase with Mailpit or Inbucket to capture mail.
- Public sign-up: `POST /auth/v1/signup` with the anon key must return "Signups not allowed".
- Reference: SD Elements guidance for T518.

**Success Criteria:**
- [ ] The unit and integration tests above pass.
- [ ] Public sign-up is rejected on the hosted project (manual check recorded).

**Status:** Pending
