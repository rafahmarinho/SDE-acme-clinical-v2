---
name: t331-enforce-policies-through-content-security-policy-c
description: Defines a strict Content-Security-Policy for the ACME Clinical React SPA (vercel.json) and the FastAPI API (middleware) that allows only self-hosted scripts, connections to the API origin and Supabase over https/wss, blocks framing and inline/eval script, and reports violations to a self-hosted endpoint.
---

# T331: Enforce policies through content security policy (CSP) or XSS protection headers

**Category:** CODE_FIX
**SD Elements:** [T331](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T331/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel."
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
A Vite SPA deployed with Vercel defaults has no CSP. Observations, patient names and maintenance notes are user-entered and rendered in the UI; any XSS (e.g. via `dangerouslySetInnerHTML` or a compromised dependency such as a 3D library) could read the Supabase session and exfiltrate PHI to any host. The SPA talks to a separate API origin and to Supabase (REST over https, Realtime over wss), so `connect-src` must be explicit.

**Secure Implementation Pattern:**
frontend/vercel.json (replace `<project-ref>` and the API host with real values; vercel.json does not interpolate env vars):
```json
{
  "headers": [{
    "source": "/(.*)",
    "headers": [{
      "key": "Content-Security-Policy",
      "value": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob: https://<project-ref>.supabase.co; font-src 'self'; connect-src 'self' https://acme-clinical-api.vercel.app https://<project-ref>.supabase.co wss://<project-ref>.supabase.co; worker-src 'self' blob:; frame-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'; upgrade-insecure-requests; report-uri https://acme-clinical-api.vercel.app/api/csp-report; report-to csp"
    }, {
      "key": "Reporting-Endpoints", "value": "csp=\"https://acme-clinical-api.vercel.app/api/csp-report\""
    }]
  }]
}
```
backend/app/core/security.py (API returns JSON only, so the policy is maximal):
```python
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; sandbox"
response.headers["Content-Security-Policy"] = API_CSP
response.headers["X-XSS-Protection"] = "0"  # legacy filter disabled; CSP is the control
```

**Implementation Guidance:**
- Keep `script-src 'self'` with no `'unsafe-inline'`/`'unsafe-eval'`. Vite production builds emit external module scripts, so no nonce is needed; do not add inline `<script>` blocks to `frontend/index.html`.
- `connect-src` lists only: the API origin (from `VITE_API_URL`), `https://<ref>.supabase.co` (Auth, PostgREST, Storage) and `wss://<ref>.supabase.co` (Realtime). Signed Storage URLs are on the same host.
- If the optional 3D view uses Three.js/React Three Fiber, bundle it via pnpm (no CDN) so `script-src 'self'` still holds; WebGL needs no extra directive. If a third-party embed is ever needed, isolate it per T1543/T1544 and add only that origin to `frame-src`.
- Use separate Vercel environments: the Preview CSP may add the preview API URL; never use wildcards like `https://*.vercel.app`.
- Report violations to a self-hosted `/api/csp-report` (see T1469). Deploy first with `Content-Security-Policy-Report-Only` in Preview, then enforce.
- CSP is defense-in-depth: keep React's default escaping and ban `dangerouslySetInnerHTML` via ESLint (`react/no-danger`).
- `X-XSS-Protection` is deprecated; set it to `0` and rely on CSP.
- Reference: SD Elements guidance for T331.

**Success Criteria:**
- [ ] Frontend responses carry the CSP above with `default-src`, `connect-src`, `form-action`, `frame-ancestors` and `report-uri` set, and no `unsafe-inline`/`unsafe-eval` in `script-src`.
- [ ] The production app (login, live monitoring via Realtime, reports download, 3D view) works with zero CSP violations in the console.
- [ ] API responses carry `default-src 'none'; frame-ancestors 'none'`; verified by T332 tests.

**Status:** Pending
