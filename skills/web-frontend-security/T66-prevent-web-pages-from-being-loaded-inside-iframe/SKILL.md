---
name: t66-prevent-web-pages-from-being-loaded-inside-iframe
description: Prevent clickjacking of the ACME Clinical web app and API (e.g. tricking a nurse into acknowledging alarms) by sending X-Frame-Options DENY, CSP frame-ancestors 'none' and X-Permitted-Cross-Domain-Policies none from the Vercel frontend config and FastAPI middleware.
---

# T66: Prevent web pages from being loaded inside iFrame

**Category:** CODE_FIX
**SD Elements:** [T66](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T66/)
**Priority:** 7/10 · **Phase:** development

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
A Vite SPA deployed on Vercel ships with no framing protection by default. A hostile page can frame the alarm or settings screen transparently and trick a logged-in clinician into clicking "Acknowledge", "Unlink monitor" or "Reset data". The 3D visualisation hint may also tempt embedding third-party viewers that require relaxed framing.

**Secure Implementation Pattern:**
```json
// frontend/vercel.json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "Content-Security-Policy",
          "value": "default-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'" },
        { "key": "X-Permitted-Cross-Domain-Policies", "value": "none" },
        { "key": "X-Content-Type-Options", "value": "nosniff" }
      ]
    }
  ]
}
```
```python
# backend/app/core/middleware.py - API responses can never be framed either
SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "X-Permitted-Cross-Domain-Policies": "none",
}
```

**Implementation Guidance:**
- Set framing headers for every path (including the SPA rewrite target `index.html`) in `frontend/vercel.json`; the app needs no framing, so use `DENY` / `frame-ancestors 'none'`.
- Keep the same headers in `SECURITY_HEADERS` applied by `SecurityHeadersMiddleware` in `backend/app/core/middleware.py`, and in `backend/vercel.json` for platform-served responses.
- Do not add `crossdomain.xml`/`clientaccesspolicy.xml` to `frontend/public`.
- CSP must be sent as an HTTP header (a `<meta>` CSP cannot set `frame-ancestors`); do not rely on JavaScript frame-busting.
- Critical actions additionally require explicit confirmation/step-up (`frontend/src/components/StepUpDialog.tsx`), which also mitigates clickjacking.
- Reference: SD Elements guidance for T66.

**Success Criteria:**
- [ ] `curl -sI https://<frontend>/alarms` shows `X-Frame-Options: DENY` and `frame-ancestors 'none'`; same for the API base URL.
- [ ] Pytest (`backend/tests/test_api_security.py`): every response, including 404/405/429 errors, carries both headers.
- [ ] Manual: embedding the frontend in an `<iframe>` from another origin is refused by the browser.

**Status:** Applied
