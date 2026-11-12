# Web front-end security (React SPA on Vercel)

Scope: `frontend/` (React + Vite + TypeScript, deployed as a static Vercel project). The API
(`backend/`) has its own headers in `backend/app/core/middleware.py`. Controls are verified by
`frontend/src/security.test.tsx` (`pnpm test -- --run`).

## Origin map (T1543)

| Role | Origin (example) | Configured in |
|------|------------------|---------------|
| Web UI (holds the Supabase session) | `https://acme-clinical.vercel.app` | Vercel project `frontend/` |
| API (FastAPI, JSON only, no HTML) | `https://acme-clinical-api.vercel.app` | `VITE_API_BASE_URL`, backend `CORS_ALLOWED_ORIGINS` |
| Supabase (Auth, PostgREST, Storage, Realtime) | `https://<project-ref>.supabase.co` + `wss://<project-ref>.supabase.co` | `VITE_SUPABASE_URL` |

There is no third-party or untrusted embed. The SPA renders no `<iframe>` (`frame-src 'none'`), and
uploaded files are never served from the SPA origin: they open in a new tab as short-lived
signed URLs on the Supabase Storage origin, checked against that exact origin by
`openSafely()` (`frontend/src/components/ExternalLink.tsx`). If an untrusted 3D/visualisation
component is ever needed, host it on its own origin, embed it with `sandbox="allow-scripts"`
(never together with `allow-same-origin`), add only that origin to `frame-src`, and exchange
messages only through one module that checks `event.origin` by strict equality, checks
`event.source` and validates payloads against a schema (T258). The test suite fails on any
cross-window `postMessage`, window `message` listener or unsandboxed iframe. The only messaging
is a same-origin `BroadcastChannel` in `src/auth/session.ts` that syncs sign-out across tabs.

## Response headers (`frontend/vercel.json`)

| Header | Value / purpose | CM |
|--------|-----------------|----|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self'`; `connect-src` = API + Supabase https/wss only; `frame-ancestors 'none'`, `frame-src 'none'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `upgrade-insecure-requests`, `report-uri`/`report-to` | T331, T332, T1469 |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` (no `preload` until a custom apex domain is chosen) | T322, T333 |
| `X-Content-Type-Options` | `nosniff` on every route, including `/assets/*` | T435, T436 |
| `X-Frame-Options` | `DENY` (legacy browsers; CSP `frame-ancestors` is the primary control) | T119 |
| `Referrer-Policy` | `strict-origin-when-cross-origin` (in-app paths with patient UUIDs never leave the origin) | T219 |
| `Permissions-Policy` | camera, microphone, geolocation, payment, USB, sensors... disabled | - |
| `Cross-Origin-Opener-Policy` / `Cross-Origin-Resource-Policy` | `same-origin` / `same-site` | T512, T1543 |
| `Cache-Control` (all non-asset paths, i.e. `index.html` and SPA routes) | `no-store, no-cache, max-age=0, must-revalidate, private` + `Pragma: no-cache` + `Expires: 0` | T64, T112 |
| `Cache-Control` (`/assets/*`, content-hashed, no patient data) | `public, max-age=31536000, immutable` | T64 |

`X-XSS-Protection: 0` disables the legacy filter (CSP is the control). No header carries a
framework or build version; `server: Vercel` / `x-vercel-id` are platform headers added at the
edge and accepted (they reveal no version). Source maps are not built (`build.sourcemap: false`),
and the SPA rewrite excludes `/assets/`, so a missing asset or `.map` returns 404 instead of
`index.html` served as script (T1873, T1874).

The SPA itself is strict-CSP compatible: Vite emits only external `<script type="module">` files
(ES modules are strict mode by spec, T325/T329), no inline scripts or event handlers, no inline
style attributes, and `assetsInlineLimit: 0` keeps every asset on `'self'`. API calls use
`credentials: "omit"`, `cache: "no-store"` and a Bearer header (`frontend/src/services/api.ts`).

### Setting the deployment-specific origins

`vercel.json` cannot interpolate environment variables, so the CSP contains the example origins
`https://acme-clinical-api.vercel.app` and `https://project-ref.supabase.co` /
`wss://project-ref.supabase.co` (matching the shape of `frontend/.env.example`). For each
deployment:

1. Replace them in `connect-src`, `img-src`, `report-uri` and `Reporting-Endpoints` with the real
   API origin (`VITE_API_BASE_URL`) and Supabase origin (`VITE_SUPABASE_URL`, both `https://` and
   `wss://`). Never use wildcards such as `https://*.vercel.app` or scheme-only sources.
2. Preview deployments that talk to a different API get their own explicit origin (separate
   branch/project config), never a wildcard.
3. The build enforces this: `cspDeploymentGuard` in `frontend/vite.config.ts` fails `vite build`
   when `VITE_API_BASE_URL` / `VITE_SUPABASE_URL` are set (always the case on Vercel) but are not
   `https://` or are missing from `connect-src`.
4. After deploy, check headers: `curl -sI https://<web>/ https://<web>/patients https://<web>/assets/<index>.js`
   and confirm CSP, HSTS (`max-age >= 31536000`), `nosniff`, `X-Frame-Options: DENY` and
   `Cache-Control: no-store` on HTML; exercise login, live monitoring (Realtime `wss`), file
   opening and reports with the DevTools console open: zero CSP violations expected.
5. Clickjacking probe (T119): from an unrelated origin load
   `<iframe src="https://<web>/alarms">` and a double-framed variant; the frame must stay empty.
   `src/main.tsx` additionally refuses to render when framed (defence in depth only).

## Decision: CSP violation reporting (T1469)

Violations are reported only to our own API, `POST <API origin>/v1/csp-report` (both `report-uri`
and the Reporting API `report-to csp`). No third-party collector is used, because reports carry
`document-uri`/`blocked-uri` values that may contain patient UUIDs in paths and signed-URL tokens
in query strings. The endpoint (backend) is unauthenticated by nature, so it must: accept only
`application/csp-report`, `application/reports+json` or `application/json` up to 8 KiB, keep a
fixed field allow-list, reduce every URL to its origin before logging, rate-limit per IP, never
echo input, always answer `204`, and log through the structured security logger (no PHI). Roll out
a CSP change first as `Content-Security-Policy-Report-Only` in a Preview deployment, then enforce.

## Decision: CSRF defence (T1541, T96)

The SPA authenticates to the API with the Supabase access token in the `Authorization: Bearer`
header; **no cookie is ever used for API authentication** (`credentials: "omit"`, the API never
reads cookies). A cross-site page cannot attach that header, so classic CSRF (auto-submitted forms,
`<img>`, `fetch(..., {mode: "no-cors"})`) reaches the API unauthenticated and is rejected with 401.
Further layers:

* Strict CORS on the API: exact SPA origins only, `allow_credentials=False`, never `*` or regex.
* JSON-only bodies: state-changing requests with a body must be `application/json` (415 otherwise),
  so any cross-origin write needs a CORS preflight that untrusted origins fail.
* No state change via GET (alarm acknowledgement, monitor binding, simulation reset/advance are
  POST/PUT/PATCH/DELETE), and multi-step flows are validated server-side (`expected_version` on
  simulation advance, `confirm` + bed availability on monitor binding, `PASSWORD_RECOVERY` session
  for password reset) (T67, T142).
* CSP `form-action 'self'` and `frame-ancestors 'none'` on the SPA.
* Origin check: a POST/PUT/PATCH/DELETE carrying an `Origin` header that is not one of the configured SPA
  origins (including `Origin: null`) is refused with 403 before routing (`SecurityHeadersMiddleware`);
  non-browser clients send no `Origin` and still need the bearer token.

Synchronizer/double-submit tokens are therefore not used (T29 decision): the Supabase access token sent in the
`Authorization` header already is a per-session, unpredictable secret that the browser never attaches
automatically, which is exactly the property an anti-CSRF token provides. **Re-open this decision** if cookie-based
authentication, HTML form posts to the API or `allow_credentials=True` are ever introduced.

Manual check: from another origin, auto-submit `<form method="POST" action="https://<api>/v1/simulation/reset">`
while logged in; the simulation must not reset (verify in the Events screen). Replaying a captured
request without the `Authorization` header must return 401.

## Decision: JSON hijacking (T166, T167)

Every API collection is returned inside the `Page` object envelope (`{"items": [...], "next_offset": ...}`);
no route returns a top-level JSON array (enforced by `backend/tests/test_api_security.py`). Responses are
`application/json` with `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`, and the API authenticates
only with the `Authorization` header, so a cross-site `<script src>` request carries no credentials and gets
401. Unpredictable URLs or `while(1);` prefixes are therefore unnecessary.

## Forms and client storage (T63, T111, T296, T219)

* Every form and free-text/number field in the clinical screens (patient search, observations,
  acknowledgement notes, maintenance notes, alarm limits, simulation, events filters, emergency
  access reason) sets `autoComplete="off"`; free-text fields also disable spellcheck so text is not
  sent to cloud spelling services. The test suite checks every `<form>`, `<input>` and
  `<textarea>` in those screens and components.
* **Login / password reset decision:** the login form keeps `autocomplete="username"` and
  `current-password`, and the reset form `new-password`, so password managers work (enabling long,
  unique passwords outweighs the shared-workstation risk, which is mitigated by idle sign-out and
  short sessions). If organisational policy forbids saved passwords, change them to `off`.
* No clinical data, search terms or drafts are written to `localStorage`, `sessionStorage`,
  IndexedDB or Cache Storage, and there is no service worker; the only persisted item is the
  Supabase session managed by supabase-js (`src/lib/supabase.ts`). The suite fails on any other use.
* Patient search text is kept in React state, never in the browser URL; only non-identifying
  filters (ward UUID, alarm flag) appear in the address bar, and patient routes use opaque UUIDs.
  The API client refuses query parameters that look like credentials or personal data
  (`buildQuery` in `src/services/api.ts`). Residual: the free-text patient search term still
  travels to the API as `GET /v1/patients?q=` (visible in Vercel request logs, not in browser
  history); moving it to a `POST /v1/patients/search` JSON body is requested from the backend owner,
  after which `api.patients` switches to it.
* New tabs open only through `ExternalLink` / `openSafely` (`noopener,noreferrer`, opener nulled,
  HTTPS-only, optional exact-origin check) (T512, T513); manual probe: a page that runs
  `if (window.opener) opener.location = "https://example.org"` must not redirect the app tab.
