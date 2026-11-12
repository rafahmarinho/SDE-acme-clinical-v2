---
name: t2270-test-to-confirm-that-password-policies-are-configu
description: Test confirming that ACME Clinical administrators can change password complexity, minimum and maximum age, history and banned-word settings, and that the new policy takes effect immediately, verifying T4.
---

# T2270: Test to confirm that password policies are configurable

**Category:** CODE_FIX
**SD Elements:** [T2270](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2270/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
The Settings screen might show the password rules as read-only text, or the backend might hard-code them, so an administrator could not tighten them. This test confirms that each policy setting can be configured and is enforced.

**Secure Implementation Pattern:**
```python
# backend/tests/test_password_policy_config.py
from tests.jwt_factory import make_token

ADMIN = {"Authorization": f"Bearer {make_token(role='administrator', aal='aal2')}"}
NURSE = {"Authorization": f"Bearer {make_token(role='nurse')}"}

async def test_admin_can_configure_all_settings(client):
    body = {"min_length": 14, "require_lower": True, "require_upper": True,
            "require_digit": True, "require_symbol": True,
            "min_age_days": 1, "max_age_days": 180, "history_count": 8,
            "banned_words": ["ward", "monitor"]}
    r = await client.put("/admin/password-policy", json=body, headers=ADMIN)
    assert r.status_code == 200
    assert (await client.get("/admin/password-policy", headers=ADMIN)).json() == body

async def test_new_policy_is_enforced(client, nurse_session):
    await client.put("/admin/password-policy", json={"banned_words": ["monitor"]}, headers=ADMIN)
    r = await nurse_session.post("/me/password", json={
        "current_password": nurse_session.pw, "new_password": "Monitor-Strong-2026!"})
    assert r.status_code == 422

async def test_non_admin_cannot_configure(client):
    r = await client.put("/admin/password-policy", json={"min_length": 4}, headers=NURSE)
    assert r.status_code == 403

async def test_policy_bounds(client):
    r = await client.put("/admin/password-policy", json={"min_length": 4}, headers=ADMIN)
    assert r.status_code == 422     # cannot go below the 8-character floor
```

**Implementation Guidance:**
- Cover each required setting: complexity, minimum and maximum age, history, and the banned-word dictionary. Add `min_age_days` to the T4 model if the organization requires a minimum age.
- Check that changes are audit-logged with the administrator's user ID and are enforced on the next password change without a redeploy.
- Manual: log in as an MFA-verified administrator, change every field in Settings, then try a change as a nurse that breaks the new rule.
- Reference: SD Elements guidance for T2270.

**Success Criteria:**
- [ ] All tests pass. Each setting can be read back, is enforced, is admin-only and is bounded by safe floors.
- [ ] An audit row exists for each policy change.

**Status:** Applied
