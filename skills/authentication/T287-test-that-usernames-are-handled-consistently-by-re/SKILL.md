---
name: t287-test-that-usernames-are-handled-consistently-by-re
description: Test that ACME Clinical staff emails (the login username) that differ only in case or trailing or leading whitespace cannot be registered twice and never resolve to another user's identity or role across the team-management API, Supabase Auth and the profiles table, verifying T286.
---

# T287: Test that usernames are handled consistently by registration system, authentication system and application

**Category:** CODE_FIX
**SD Elements:** [T287](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T287/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe"
> (EN: limit settings, reports and team management)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Administrators create staff in team management, and Supabase Auth authenticates them by email. If the backend stores `" Nurse@acme.test"` in `profiles` while GoTrue stores the trimmed, lowercased value, role lookups by email could attach one person's role to another account.

**Secure Implementation Pattern:**
```python
# backend/tests/test_username_consistency.py
import pytest
from tests.jwt_factory import make_token
ADMIN = {"Authorization": f"Bearer {make_token(role='administrator', aal='aal2')}"}

VARIANTS = ["joe@acme.test", "Joe@acme.test", "joe@acme.test ", " joe@acme.test",
            "joe@ACME.test", "joe@acme.test​"]

async def test_variants_cannot_create_second_account(client, fake_admin_api):
    first = await client.post("/admin/staff", headers=ADMIN, json={
        "email": VARIANTS[0], "full_name": "Joe Test", "role": "nurse", "employee_number": "E1"})
    assert first.status_code == 202
    for i, v in enumerate(VARIANTS[1:], start=2):
        r = await client.post("/admin/staff", headers=ADMIN, json={
            "email": v, "full_name": "Joe Clone", "role": "administrator", "employee_number": f"E{i}"})
        assert r.status_code in (202, 422)
    assert fake_admin_api.created_emails == ["joe@acme.test"]   # only one account exists

@pytest.mark.parametrize("v", VARIANTS[1:])
def test_canonical_form(v):
    from app.services.identity import canonical_email
    assert canonical_email(v.strip("​ ")) == "joe@acme.test"
```

**Implementation Guidance:**
- Registration: send each variant to `POST /admin/staff`. Variants must either be rejected (whitespace, invisible characters) or normalize to the existing account without creating a second account or changing its role.
- Authentication: against local Supabase, log in with `"Joe@acme.test"` and `"joe@acme.test"` and check that both return the same `sub`. Log in with the trailing-space variant and check that the frontend trims it before calling (T286) and no different identity results.
- Application: check that `/me` resolves role and profile by `claims["sub"]` (UUID), never by the email string.
- Reference: SD Elements guidance for T287.

**Success Criteria:**
- [ ] Only one auth user and profile exists after all registration variants are submitted.
- [ ] All login variants resolve to the same UUID, and no variant obtains a different role.

**Status:** Pending
