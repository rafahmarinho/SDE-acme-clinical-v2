---
name: t2276-test-to-confirm-that-authorization-and-authenticat
description: Test that ACME Clinical identifies human users, simulated monitors and the simulation service, authenticates them, assigns RBAC roles, checks permissions on every request, offers logout on every authenticated screen and never exposes nonpublic data publicly.
---

# T2276: Test to confirm that authorization and authentication controls are in place for access to resources

**Category:** CODE_FIX
**SD Elements:** [T2276](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2276/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "conseguir para simular as ações). Use pacientes fictícios e monitores simulados para mostrar"
> (EN: "...if you can, to simulate the actions). Use fictional patients and simulated monitors to show")
> Source: specs/PRD.md, line 29

> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: "...connection loss. Have nurse, physician, biomedical technician and administrator profiles.")
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
Human logins via Supabase Auth would be built, but the simulated monitors and the simulation engine would write readings through an unauthenticated endpoint or with the service key. Logout may exist only in the profile menu of some screens.

**Secure Implementation Pattern:**
```python
# backend/tests/test_authn_authz_controls.py
async def test_device_identity_required(client):
    r = await client.post("/api/ingest/readings", json={"monitor_id": MON, "hr": 80})
    assert r.status_code == 401                         # monitors must authenticate

async def test_device_cannot_act_as_user(device_client):
    assert (await device_client.get("/api/patients")).status_code == 403

@pytest.mark.parametrize("role", ["nurse", "physician", "biomedical_technician", "administrator"])
async def test_role_assigned_and_checked(client_as, role):
    me = (await client_as(role).get("/api/me")).json()
    assert me["role"] == role and me["permissions"]

async def test_logout_revokes(client_as, nurse):
    c = client_as(nurse)
    await c.post("/api/auth/logout")                   # calls supabase auth sign_out(scope="global")
    assert (await c.get("/api/patients")).status_code == 401
```
```ts
// frontend/src/components/AppShell.test.tsx (vitest + testing-library)
it.each(protectedScreens)("%s shows a logout control", async (path) => {
  renderWithSession(path);
  expect(await screen.findByRole("button", { name: /log out/i })).toBeInTheDocument();
});
```

**Implementation Guidance:**
- Identify three subject types: staff (Supabase Auth JWT), simulated monitors (per-device credential or HMAC key held by the simulator, mapped to `devices.id`), and the simulation service (`system:simulator` identity with only ingest/advance rights).
- Verify RBAC: each staff row has a role; `GET /me` returns role and effective permissions from `backend/app/core/security.py`.
- Verify a permission check precedes processing for every resource (reuse the route-matrix test from T2274).
- Logout: `AppShell` in `frontend/src/components` renders logout on every authenticated screen; backend revocation invalidates refresh tokens.
- Verify nonpublic content (Storage objects, Realtime channels, `/openapi.json`) requires authentication.
- Reference: SD Elements guidance for T2276.

**Success Criteria:**
- [ ] Device and service identities are authenticated and limited to ingest endpoints.
- [ ] Every protected screen has logout (frontend test) and logout invalidates the session.
- [ ] No nonpublic resource is reachable anonymously.

**Status:** Applied
