---
name: t17-do-not-only-rely-on-client-side-authorization
description: Ensure ACME Clinical enforces every role check (nurse, physician, biomedical technician, administrator) on the FastAPI server and in Supabase RLS, treating the role-adapted React navigation and RoleGuard only as UX.
---

# T17: Do not only rely on client-side authorization

**Category:** CODE_FIX
**SD Elements:** [T17](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T17/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> "usuário."
> (EN: filters, loading states and error messages. Adapt navigation to user profiles.)
> Source: specs/PRD.md, lines 13-15

**What the spec implies (naive approach):**
"Adapt navigation to user profiles" is most simply done by hiding menu items and wrapping routes in a `<RoleGuard>` in React, while the API endpoints behind them only check that a token is present. Any authenticated nurse can then call `PATCH /settings/security`, `POST /simulation/reset` or `POST /staff` directly with curl, or edit the role in local storage.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
def require(*perms: Perm):
    async def dep(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
        # role comes from the database (staff_profiles), not from the client or user_metadata
        if not all(p in ROLE_PERMISSIONS[principal.role] for p in perms):
            await _deny(request, principal, "authz_denied", {"required": [p.value for p in perms]})
            raise FORBIDDEN
        return principal
    dep.__acme_perms__ = frozenset(perms)
    return dep

# backend/app/routers/settings.py
@router.patch("/security", response_model=SecuritySettingsOut)
async def update_security(body: SecuritySettingsIn,
                          principal: Principal = Depends(require_recent_auth(Perm.settings_manage))): ...

# backend/app/main.py - fail startup if any route lacks a server-side check
assert_routes_protected(app, production=settings.is_production)
```
```tsx
// frontend/src/components/RoleGuard.tsx - UX only; the API still returns 403
export function RoleGuard({ allow, children }: { allow: Role[]; children: ReactNode }) {
  const { profile } = useAuth();
  return profile && allow.includes(profile.role) ? <>{children}</> : <Navigate to="/" replace />;
}
```

**Implementation Guidance:**
- Every router function in `backend/app/routers/*.py` depends on `require`/`require_any`/`require_recent_auth` from `backend/app/core/security.py`; `assert_routes_protected` in `backend/app/main.py` blocks startup if any non-public route lacks one.
- Resolve the role server-side from `public.staff_profiles` (via `fetch_staff_identity` in `backend/app/db.py` / `current_staff_role()` SQL), never from JWT `user_metadata`, request bodies or headers.
- Mirror the checks in the database: RLS policies and `has_permission()` in `supabase/migrations/0002_roles_rls.sql` / `0003_authz_rbac.sql` protect any direct Supabase (PostgREST/Realtime/Storage) access from the browser.
- Keep `frontend/src/components/RoleGuard.tsx` and the navigation in `frontend/src/App.tsx` for usability only; handle 403 from the API gracefully in `frontend/src/services/api.ts`.
- Reference: SD Elements guidance for T17.

**Success Criteria:**
- [ ] Pytest matrix (`backend/tests/test_authorization.py`): for every route and every role, `role_may_call(route, role)` matches the documented permission table in `docs/security/authorization.md`, and forbidden calls return 403.
- [ ] Pytest: nurse token calling `POST /simulation/reset`, `PATCH /settings/security`, `POST /staff` -> 403 even with a forged `role` in the body or token metadata.
- [ ] `frontend/src/components/RoleGuard.test.tsx` confirms UX hiding; no API security depends on it.

**Status:** Applied
