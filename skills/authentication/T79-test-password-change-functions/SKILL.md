---
name: t79-test-password-change-functions
description: Security tests verifying that every ACME Clinical password change path (profile screen, backend /me/password, direct Supabase updateUser) rejects changes without the correct current password, verifying T3.
---

# T79: Test password change functions

**Category:** CODE_FIX
**SD Elements:** [T79](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T79/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Profile and settings screens are where users change passwords. Without a test, a refactor could make the screen call `supabase.auth.updateUser({ password })` directly, or the backend could stop checking `current_password`, and the change would go unnoticed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_password_change.py
import pytest, respx, httpx
from httpx import ASGITransport, AsyncClient
from app.main import app
from tests.jwt_factory import make_token

TOKEN_URL = "https://test.supabase.co/auth/v1/token"

@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t",
                       headers={"Authorization": f"Bearer {make_token(role='nurse')}"})

@respx.mock
async def test_missing_old_password_rejected(client):
    r = await client.post("/me/password", json={"new_password": "N3w-Strong-Passphrase!"})
    assert r.status_code == 422

@respx.mock
async def test_wrong_old_password_rejected(client):
    respx.post(url__startswith=TOKEN_URL).mock(return_value=httpx.Response(400))
    admin = respx.put(url__regex=r".*/auth/v1/admin/users/.*")
    r = await client.post("/me/password", json={"current_password": "wrong",
                                                "new_password": "N3w-Strong-Passphrase!"})
    assert r.status_code == 400
    assert not admin.called          # password was NOT updated
```

**Implementation Guidance:**
- Automated (backend): add the tests above plus a success case, and assert that the admin update is called only after the old password verifies.
- Automated (frontend): a Vitest test checks that the Profile screen never calls `supabase.auth.updateUser` with a `password` key. Spy on it and fail if it is called.
- Manual: search every screen in `frontend/src/screens/` (Profile, Settings, Team Management) for password change features. For each, try changing the password (a) without the old password and (b) with a wrong one. Also try `supabase.auth.updateUser({ password })` from the browser console on an old session, and expect a reauthentication requirement because `secure_password_change` is on.
- Administrator-initiated resets for other staff must send a recovery link, not set a password chosen by the admin.
- Reference: SD Elements guidance for T79.

**Success Criteria:**
- [ ] The backend tests for missing, wrong and correct old passwords pass in CI.
- [ ] The frontend spy test confirms no direct `updateUser({ password })` call.
- [ ] A manual console test record shows that the direct update requires reauthentication.

**Status:** Applied
