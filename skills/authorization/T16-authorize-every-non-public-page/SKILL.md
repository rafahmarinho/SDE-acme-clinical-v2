---
name: t16-authorize-every-non-public-page
description: Apply an explicit authentication and authorization check to every non-public ACME Clinical API route and screen, with a short whitelist of public pages (login, password recovery, health) and no alternative unauthenticated access paths.
---

# T16: Authorize every non-public page

**Category:** CODE_FIX
**SD Elements:** [T16](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T16/)
**Priority:** 6/10 · **Phase:** development

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Login and password recovery are public, everything else should not be — but developers often add new routers without auth dependencies, or protect only the React routes. Supabase tables left without RLS are also reachable directly with the public anon key.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
PUBLIC_ROUTES: frozenset[str] = frozenset({"/health", "/auth/password-reset/request"})

# backend/app/main.py
from app.routers import alarms, patients, wards, devices, thresholds, reports, staff, simulation
from app.routers._base import protected_router

api = protected_router(prefix="/api")      # Depends(get_current_user) on every route
for r in (patients, wards, alarms, devices, thresholds, reports, staff, simulation):
    api.include_router(r.router)
app.include_router(api)
app.include_router(public.router)          # only routes in PUBLIC_ROUTES
```
```tsx
// frontend/src/lib/RequireAuth.tsx  (UX only; the API is the enforcement point)
export function RequireAuth({ perm, children }: { perm?: Perm; children: ReactNode }) {
  const { session, permissions, loading } = useSession();
  if (loading) return <LoadingScreen />;
  if (!session) return <Navigate to="/login" replace />;
  if (perm && !permissions.includes(perm)) return <Navigate to="/forbidden" replace />;
  return <>{children}</>;
}
```

**Implementation Guidance:**
- Keep `PUBLIC_ROUTES` in `backend/app/core/security.py` as the single whitelist (see T373) and mount every other router under `protected_router()`.
- Add the per-function `require(...)` permission on top (T2141); authentication alone is not authorization.
- Enable RLS on every table in `supabase/migrations/0001_schema.sql` so the anon key cannot bypass the API; Storage buckets are private and served via short-lived signed URLs after an API check.
- Frontend: wrap all screens except `/login`, `/reset-password` in `RequireAuth` in `frontend/src/screens`; this only adapts navigation.
- Disable `/docs`, `/redoc`, `/openapi.json` in production.
- Reference: SD Elements guidance for T16.

**Success Criteria:**
- [ ] Route introspection test shows every route outside `PUBLIC_ROUTES` depends on `get_current_user`.
- [ ] Anonymous Supabase client query on any table returns zero rows / permission denied.
- [ ] Unauthenticated visit to any protected screen redirects to login.

**Status:** Pending
