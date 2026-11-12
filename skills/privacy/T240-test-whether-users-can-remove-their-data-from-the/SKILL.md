---
name: t240-test-whether-users-can-remove-their-data-from-the
description: Test recipe confirming ACME Clinical staff can request removal of their account/personal data, that removal requires re-authentication, and that removal is evidenced and complete (profile, auth user, avatar files).
---

# T240: Test whether users can remove their data from the system

**Category:** CODE_FIX
**SD Elements:** [T240](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T240/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you can create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
"Gestão da equipe" and "perfil" suggest admins create staff accounts and users edit profiles, but no removal path. A naive build has no delete option, or a single DELETE call without re-authentication, leaving the Supabase Auth user, avatar files and name in alarm acknowledgements behind.

**Secure Implementation Pattern:**
```python
# backend/tests/test_account_removal.py
import pytest

@pytest.mark.asyncio
async def test_removal_requires_reauth(client, nurse_token):
    r = await client.post("/me/delete", headers=auth(nurse_token), json={})
    assert r.status_code in (400, 401)

@pytest.mark.asyncio
async def test_removal_with_password_erases_personal_data(client, nurse, db, storage):
    r = await client.post("/me/delete", headers=auth(nurse.token),
                          json={"current_password": nurse.password})
    assert r.status_code == 202
    assert await db.fetchval("select count(*) from profiles where id=$1", nurse.id) == 0
    assert await db.fetchval("select count(*) from auth.users where id=$1", nurse.id) == 0
    assert await storage.list(prefix=f"avatars/{nurse.id}/") == []
    # acknowledgements kept but de-identified
    ack = await db.fetchrow("select acknowledged_by_name from alarm_events "
                            "where acknowledged_by_ref=$1 limit 1", nurse.pseudo_ref)
    assert ack is None or ack["acknowledged_by_name"] is None
    # old token no longer works
    assert (await client.get("/me", headers=auth(nurse.token))).status_code == 401
```

**Implementation Guidance:**
- Target the removal endpoint from T179 in `backend/app/routers/profile.py` and the account section of the profile screen in `frontend/src/screens/`.
- Step 1: confirm a "Delete my account" / "Request removal" option is reachable from the profile or settings menu; test fails if absent.
- Step 2: assert removal without `current_password` (or email confirmation) is rejected.
- Step 3: assert data erasure across `profiles`, Supabase Auth (`auth.admin.delete_user` via service role), Storage, and de-identification of retained clinical audit records.
- Check evidence: `purge_log`/deletion log entry and documented retention exceptions (clinical audit records retained in de-identified form).
- Reference: SD Elements guidance for T240.

**Success Criteria:**
- [ ] Removal option is visible from the profile screen (frontend test with vitest/testing-library).
- [ ] Removal without re-authentication returns 400/401.
- [ ] After removal, profile, auth user and Storage files are gone and old sessions are rejected.
- [ ] A deletion log entry with no personal data exists.

**Status:** Pending
