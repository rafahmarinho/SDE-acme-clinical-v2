---
name: t77-test-for-single-factor-authentication
description: Security test proving that ACME Clinical administrator capabilities cannot be used with a password-only (Supabase AAL1) session, and that a second TOTP factor (AAL2) is required, verifying the control from T1.
---

# T77: Test for single-factor authentication

**Category:** CODE_FIX
**SD Elements:** [T77](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T77/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: Have nurse, physician, biomedical technician and administrator profiles.)
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
With only "login por e-mail e senha" (email and password login) in the PRD, an administrator would get full access after one factor. Without a test, an MFA guard added to the UI could be missing from the API or RLS, and a password-only token could still manage staff.

**Secure Implementation Pattern:**
```python
# backend/tests/test_single_factor.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from tests.jwt_factory import make_token   # signs with a test JWKS that verify_supabase_jwt trusts

ADMIN_ENDPOINTS = [("GET", "/admin/staff"), ("PUT", "/admin/password-policy"),
                   ("POST", "/simulation/reset")]

@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
async def test_admin_rejects_password_only_session(method, path):
    token = make_token(role="administrator", aal="aal1", amr=[{"method": "password"}])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.request(method, path, headers={"Authorization": f"Bearer {token}"}, json={})
    assert r.status_code == 401

@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
async def test_admin_allows_two_factor_session(method, path):
    token = make_token(role="administrator", aal="aal2",
                       amr=[{"method": "password"}, {"method": "totp"}])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.request(method, path, headers={"Authorization": f"Bearer {token}"}, json={})
    assert r.status_code not in (401, 403)
```

**Implementation Guidance:**
- Automated: add the tests above to `backend/tests/` and keep `ADMIN_ENDPOINTS` in sync with every route that depends on `require_admin_aal2`. A further test can list the app's routes and fail if any `/admin` route lacks that dependency.
- Database: run a SQL test against local Supabase that sets `request.jwt.claims` to an administrator with `aal = aal1` and checks that inserts and updates on admin tables are denied by RLS.
- Manual: log in as a demo administrator with password only, skip MFA, then try the Team Management screen and direct API calls with the access token. The test fails if any data is shown or changed.
- Reference: SD Elements guidance for T77.

**Success Criteria:**
- [ ] All admin endpoints return 401 for aal1 administrator tokens in CI.
- [ ] RLS SQL test denies aal1 writes to admin-managed tables.
- [ ] A manual test record shows that the admin UI cannot be reached without TOTP.

**Status:** Applied
