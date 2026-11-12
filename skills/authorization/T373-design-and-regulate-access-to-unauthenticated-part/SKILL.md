---
name: t373-design-and-regulate-access-to-unauthenticated-part
description: Define and enforce a single explicit whitelist of ACME Clinical public pages and API routes (login, password recovery, health check, static assets) that require no authentication, keeping them lightweight and rate-limited.
---

# T373: Design and regulate access to unauthenticated parts of the application

**Category:** CODE_FIX
**SD Elements:** [T373](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T373/)
**Priority:** 8/10 · **Phase:** architecture-design

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
The public surface is implicit: whatever routes happen not to have an auth dependency. Over time this grows (debug endpoints, `/docs`, "temporary" demo reset), and nobody can tell which pages are intentionally public.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py -- the single, reviewed public whitelist
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/health"),                          # liveness only, no data
    ("POST", "/auth/password-reset/request"),    # generic response, rate-limited
})
```
```ts
// frontend/src/lib/publicRoutes.ts
export const PUBLIC_SCREENS = ["/login", "/forgot-password", "/reset-password"] as const;
```
`frontend/vercel.json` (SPA fallback only; it does not create extra public API surface):
```json
{ "rewrites": [{ "source": "/((?!assets/).*)", "destination": "/index.html" }] }
```

**Implementation Guidance:**
- Keep the whitelist in `backend/app/core/security.py` and `frontend/src/lib/publicRoutes.ts`; any change needs security review (CODEOWNERS on these files).
- Public screens are simple: login, forgot/reset password. Login itself is handled by Supabase Auth directly from the frontend; the backend exposes only what is listed.
- `/health` returns `{"status":"ok"}` without version, DB or environment details.
- Apply rate limiting to public endpoints (password reset request) and return identical responses for existing/non-existing emails.
- Static assets (Vite build) are public by nature; ensure no `.env`, source maps with secrets, or `seed.sql` are deployed in `frontend/dist`.
- Reference: SD Elements guidance for T373.

**Success Criteria:**
- [ ] The whitelist exists in one place per tier and is referenced by the startup guard (T2141) and tests (T84, T2282).
- [ ] `/health` exposes no sensitive information.
- [ ] Public endpoints are rate-limited (test sends N+1 requests and receives 429).

**Status:** Applied
