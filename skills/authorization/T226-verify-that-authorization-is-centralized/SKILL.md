---
name: t226-verify-that-authorization-is-centralized
description: Review and automatically check that all ACME Clinical authorization decisions call the central backend/app/core/security.py module and RLS helpers, with no hard-coded role or user checks in routers, services or React components.
---

# T226: Verify that authorization is centralized

**Category:** CODE_FIX
**SD Elements:** [T226](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T226/)
**Priority:** 9/10 · **Phase:** testing

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: "...filters, loading states and error messages. Adapt the navigation to the user profiles")
> Source: specs/PRD.md, line 13

**What the spec implies (naive approach):**
"Adapt navigation to profiles" tends to produce role checks in many React components and copy-pasted `if user.role in (...)` checks in routers. Over time they diverge, and whichever check is missing becomes a bypass.

**Secure Implementation Pattern:**
```python
# backend/tests/test_authz_centralized.py -- static guard against scattered checks
import ast, pathlib

FORBIDDEN_ATTRS = {"role", "is_admin"}
ALLOWED = {pathlib.Path("app/core/security.py")}

def test_no_role_comparisons_outside_security_module():
    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        if path in ALLOWED:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Compare):
                names = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
                if names & FORBIDDEN_ATTRS:
                    offenders.append(f"{path}:{node.lineno}")
    assert offenders == [], offenders
```
```ts
// frontend: an ESLint rule bans `role ===` outside src/lib/permissions.ts
// .eslintrc: "no-restricted-syntax": ["error", { "selector": "BinaryExpression[left.property.name='role']",
//   "message": "Use can(perm) from src/lib/permissions.ts" }]
```

**Implementation Guidance:**
- Manually review `backend/app/routers/*.py` and `backend/app/services/*.py`: each decision must be `Depends(require(Perm.X))` or a helper like `assert_patient_access()` from `backend/app/core/security.py`.
- Add the AST test above to CI; extend it to flag comparisons against literal emails/user IDs.
- Review SQL: all RLS policies call shared helpers (`public.has_permission()`, `public.can_access_patient()`), not inline role literals scattered across policies.
- Frontend: only `frontend/src/lib/permissions.ts` (`can(perm)`) reads permissions, fed from `GET /me`; document that this is UX only.
- Reference: SD Elements guidance for T226.

**Success Criteria:**
- [ ] AST test and ESLint rule pass with zero exceptions outside the central modules.
- [ ] Code review checklist entry "authorization via central module" is part of the PR template.
- [ ] RLS policies reference only helper functions (pgTAP or grep check over `supabase/migrations`).

**Status:** Applied
