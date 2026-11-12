---
name: t2282-test-to-confirm-that-unauthenticated-parts-of-the
description: Test that the whitelisted public parts of ACME Clinical (login, password recovery screens, health check) remain reachable without a session, while nothing else is.
---

# T2282: Test to confirm that unauthenticated parts of the application are accessible

**Category:** CODE_FIX
**SD Elements:** [T2282](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2282/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Over-eager global guards (a FastAPI dependency on the whole app, or a React guard wrapping the router root) can accidentally lock users out of the password-recovery flow, or redirect-loop the login page, which pushes developers toward ad-hoc exemptions.

**Secure Implementation Pattern:**
```python
# backend/tests/test_public_routes.py
import pytest
from app.core.security import PUBLIC_ROUTES

@pytest.mark.parametrize("method,path", sorted(PUBLIC_ROUTES))
async def test_public_route_reachable_without_auth(client, method, path):
    r = await client.request(method, path, json={"email": "nobody@example.test"} if method == "POST" else None)
    assert r.status_code in (200, 202), r.text

async def test_password_reset_response_is_generic(client):
    a = await client.post("/auth/password-reset/request", json={"email": "nurse.demo@acme.test"})
    b = await client.post("/auth/password-reset/request", json={"email": "unknown@acme.test"})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
```
```ts
// frontend/src/screens/public.test.tsx
it.each(PUBLIC_SCREENS)("%s renders without a session", async (path) => {
  renderApp(path, { session: null });
  expect(screen.queryByText(/redirecting/i)).toBeNull();
  expect(await screen.findByRole("main")).toBeInTheDocument();
});
```

**Implementation Guidance:**
- Drive the test from the same whitelist (`PUBLIC_ROUTES`, `PUBLIC_SCREENS`) defined per T373 so the test and the guard cannot drift.
- Check the password-reset email link (Supabase redirect to `/reset-password`) opens without an existing session.
- Pair with T84: public routes reachable, all other routes 401.
- Run against a Vercel preview to verify rewrites in `frontend/vercel.json` don't break public screens.
- Reference: SD Elements guidance for T2282.

**Success Criteria:**
- [ ] All whitelisted routes/screens load anonymously in CI.
- [ ] Password-reset flow works end-to-end from the email link without a prior session.
- [ ] No non-whitelisted route is reachable (covered jointly with T84).

**Status:** Pending
