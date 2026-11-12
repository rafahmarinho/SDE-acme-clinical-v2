---
name: t238-test-that-users-can-review-and-update-their-person
description: Test recipe verifying ACME Clinical staff can review and edit every personal field in their profile, and that profile data is not accessible after logout.
---

# T238: Test that users can review and update their personal information

**Category:** CODE_FIX
**SD Elements:** [T238](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T238/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A "perfil" screen will likely show name and role but only allow editing the display name, while email, phone or a staff number derived from personal data stay read-only. After logout, cached profile data may remain in React state or localStorage and be reachable via the back button.

**Secure Implementation Pattern:**
```python
# backend/tests/test_profile_review_update.py
import pytest

EDITABLE = {"full_name": "Alex Grey", "phone": "+1 555 0100",
            "job_title": "Charge Nurse", "preferred_language": "en"}

@pytest.mark.asyncio
async def test_all_personal_fields_reviewable_and_editable(client, nurse):
    me = (await client.get("/me", headers=auth(nurse.token))).json()
    assert {"full_name", "email", "phone", "job_title"} <= me.keys()
    r = await client.patch("/me", headers=auth(nurse.token),
                           json=EDITABLE | {"current_password": nurse.password})
    assert r.status_code == 200
    assert {k: r.json()[k] for k in EDITABLE} == EDITABLE

@pytest.mark.asyncio
async def test_email_change_requires_confirmation(client, nurse):
    r = await client.post("/me/email", headers=auth(nurse.token),
                          json={"new_email": "new@example.test", "current_password": nurse.password})
    assert r.json()["status"] == "confirmation_sent"

@pytest.mark.asyncio
async def test_profile_inaccessible_after_logout(client, nurse):
    await client.post("/auth/logout", headers=auth(nurse.token))
    assert (await client.get("/me", headers=auth(nurse.token))).status_code == 401
```

**Implementation Guidance:**
- Test the `/me` endpoints implemented for T177 in `backend/app/routers/profile.py`.
- Step 1: assert the profile response/screen shows all personal fields defined in `docs/security/data-classification.md` for staff.
- Step 2: edit each field; email change goes through Supabase `update_user` with confirmation. Role is not personal data and stays admin-controlled.
- Step 3: after logout (Supabase `signOut` + server-side session revocation), `/me` returns 401 and the frontend profile route redirects to login; add a vitest test that the auth store and query cache are cleared on logout (`frontend/src/hooks/`).
- Reference: SD Elements guidance for T238.

**Success Criteria:**
- [ ] All staff personal fields are visible on the profile screen.
- [ ] Every personal field is editable (email via confirmation flow).
- [ ] `/me` returns 401 after logout; profile route redirects to login.
- [ ] Tests above pass in CI.

**Status:** Pending
