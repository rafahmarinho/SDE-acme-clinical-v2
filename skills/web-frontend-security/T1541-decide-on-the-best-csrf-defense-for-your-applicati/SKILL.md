---
name: t1541-decide-on-the-best-csrf-defense-for-your-applicati
description: Records and enforces the ACME Clinical CSRF defense decision: the cross-origin React SPA authenticates to FastAPI with Supabase JWTs in the Authorization header (no cookies), so the chosen defense is a secure CORS policy plus JSON-only, preflight-requiring state-changing endpoints and no cookie-based auth.
---

# T1541: Decide on the best CSRF defense for your application

**Category:** CODE_FIX
**SD Elements:** [T1541](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T1541/)
**Priority:** 7/10 · **Phase:** architecture-design

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel."
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
State-changing actions exist (acknowledge alarm, bind monitor to bed, record observation, reset simulation, manage team). A developer might later "simplify" auth by moving the token into a cookie for the API, or accept form-encoded bodies, which would make these actions forgeable from any site.

**Decision (flowchart outcome):**
1. State-changing operations: yes. 2. Browser-automatic credentials: **no** — Supabase JWT sent as `Authorization: Bearer` by `frontend/src/services/api.ts`; no cookies or Basic auth. Therefore classic CSRF does not apply. Dynamic server pages: no (SPA). Front and back on different origins → **secure CORS policy** (T318), plus JSON-only bodies so every cross-origin write needs a preflight. Synchronizer/double-submit tokens are not used.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=True)  # header only; cookies are never read

async def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    return verify_supabase_jwt(creds.credentials)  # signature, exp, aud, role claim

async def require_json(request: Request):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        ct = request.headers.get("content-type", "").split(";")[0].strip()
        if ct != "application/json":
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "JSON required")

# backend/app/main.py
app = FastAPI(dependencies=[Depends(require_json)])
```
```typescript
// frontend/src/services/api.ts
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const res = await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
    ...init, credentials: "omit",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${data.session?.access_token}`, ...init.headers },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json() as Promise<T>;
}
```

**Implementation Guidance:**
- Document the decision above in README "Security" section so future changes (cookies, form posts) trigger a re-review.
- Exempt only the unauthenticated `/api/csp-report` endpoint (T1469) from `require_json`, since browsers send `application/csp-report`; it changes no clinical state. The SPA client always sends `Content-Type: application/json`, including on bodiless DELETEs.
- Never use GET for state changes (ack alarm, bind monitor, reset simulation) in `backend/app/routers/*`.
- Keep CORS `allow_credentials=False` and an exact origin allow-list (T318). File uploads go directly to Supabase Storage with the user's JWT, or to a JSON/base64 or authenticated multipart endpoint that still requires the Bearer header (an attacker page cannot set it).
- If cookie-based auth is ever introduced, re-run this decision: same-site cookies + double-submit token are then required.
- Supabase Auth's own endpoints (login, password recovery) use the anon key + JSON; keep Supabase "Site URL" and redirect allow-list restricted to the SPA origin.
- Reference: SD Elements guidance for T1541.

**Success Criteria:**
- [ ] README states the CSRF decision (Bearer header + strict CORS + JSON-only) explicitly.
- [ ] No API route reads auth from cookies; all state-changing routes reject non-JSON bodies with 415.
- [ ] Verified by T96 tests.

**Status:** Applied
