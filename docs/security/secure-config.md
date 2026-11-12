# Secure configuration, cryptography and supply chain

Configuration is code: every change goes through a pull request (CI runs the tests below) and, for database-managed
settings, through the administrator Settings screen, which audits each change and flags drift from the approved
baseline. Tests: `backend/tests/test_secure_config.py`.

## 1. Environment settings (API, `backend/app/core/config.py`)

Secure defaults: if a variable is missing the API is in **production** mode; required secrets have no default and the
API refuses to start without them.

| Variable | Purpose | Options | Default | Security relevance / impact |
|---|---|---|---|---|
| `APP_ENV` | runtime mode | `production`, `development`, `test` | `production` | production disables docs/OpenAPI, requires `https://` URLs and origins, and refuses to start if any route lacks authentication/authorization |
| `ENABLE_DOCS` | interactive docs outside production | `true`/`false` | `false` | ignored in production; exposes the API surface when on |
| `SUPABASE_URL` | Supabase project | `https://<ref>.supabase.co` | required | must be `https://` (only `http://localhost` with `APP_ENV=development`) |
| `SUPABASE_ANON_KEY` | public key (also used to re-verify passwords) | string | required | public, but must not be empty/placeholder |
| `SUPABASE_SERVICE_ROLE_KEY` | Admin/Storage API (signed URLs, erasure, file purge) | secret | required | **Secret.** Bypasses RLS: backend only, Vercel *Sensitive* env var, never `VITE_*` |
| `SUPABASE_JWT_SECRET` | verifies access tokens (HS256) | secret, >= 32 chars | required | **Secret.** Token forgery if leaked |
| `SUPABASE_JWT_AUDIENCE` | expected `aud` | string | `authenticated` | |
| `DATABASE_URL` | Postgres DSN of the least-privilege `acme_api` role | DSN with `sslmode=verify-full` | required | **Secret.** `sslmode=require`/`disable` are rejected: TLS with certificate and host-name verification only |
| `CORS_ALLOWED_ORIGINS` | SPA origins | comma-separated `https://` origins | empty (deny all) | never `*`; credentials are not allowed (bearer tokens) |
| `MAX_REQUEST_BYTES` / `MAX_UPLOAD_BYTES` | body limits | 1 KiB-10 MiB / 1 KiB-50 MiB | 1 MiB / 5 MiB | DoS protection |
| `RATE_LIMIT_PER_MINUTE` / `AUTH_RATE_LIMIT_PER_MINUTE` | throttling | 1-10000 / 1-1000 | 120 / 10 | brute force and abuse protection (429) |
| `MAX_PAGE_SIZE` | list size cap | 1-1000 | 100 | result-set bound |

Frontend (`frontend/.env.example`) receives only public values: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`,
`VITE_API_BASE_URL`. CI fails if the built bundle contains a service-role key or JWT secret marker.

## 2. Database-managed security settings (Settings screen, `/v1/settings/security`)

Administrator-only (`settings:manage`); other roles get 403 for read and write. Values outside the baseline are
rejected by the API (422) and by `CHECK` constraints.

| Setting | Baseline (allowed) | Default | Impact |
|---|---|---|---|
| `password_min_length` | 12-128 | 12 | password strength (enforced by Supabase Auth and the API) |
| `session_idle_minutes` | 5-60 | 15 | idle sign-out |
| `session_absolute_hours` | 1-24 | 12 | absolute session lifetime |
| `max_concurrent_sessions` | 1-10 | 2 | oldest sessions revoked first |
| `lockout_threshold` | 3-10 | 5 | failed sign-ins before lockout |
| `lockout_minutes` | 5-120 | 15 | lockout duration |
| `require_mfa_for_admin` | true/false | true | administrators need `aal2`; turning it off asks for confirmation |
| `data_retention_days` | 30-3650 | 365 | retention of readings/resolved alarms and of deactivated staff accounts |

**Integrity.** `GET /v1/settings/security/report` returns the SHA-256 fingerprint of these values, the last approved
fingerprint (`POST /v1/settings/security/approve`, stored in `security_settings_approvals`), a `drift` flag, the
read-only environment flags and the component versions; the Settings screen shows a warning on drift (for example a
change made directly in the database) and lets an administrator download the report. All changes are audited.

## 3. Insecure demo settings (turn off / replace for real data)

* Demo staff accounts created by `python -m app.cli create-demo-staff` (random passwords printed once): delete them or
  rotate passwords before real use; the command refuses to run in production without `--allow-demo`.
* The demo seed (`supabase/seed.sql`) contains fictitious patients only; never load it into a real environment.
* The simulation reset (Simulation screen, admin only, typed confirmation) deletes readings, alarms and observations.
* `APP_ENV=development` / `ENABLE_DOCS=true` must never be set on the production Vercel project.

## 4. Cryptography inventory (T446/T445/T587)

| Use | Library / service | Algorithm | Notes |
|---|---|---|---|
| Password hashing | Supabase Auth | bcrypt | the app never stores or hashes passwords |
| Access-token verification | PyJWT (`pyjwt[crypto]`) | HS256 with the project's >= 256-bit JWT secret | explicit `algorithms=["HS256"]`, `aud`, `iss`, `exp`, `iat`, `sub` required; `alg=none` and other algorithms rejected |
| Audit hash chain | PostgreSQL `pgcrypto` | SHA-256 | `events_hash_chain()` |
| Device secret storage | `pgcrypto` / `hashlib` | SHA-256 of a 256-bit random secret | constant-time comparison |
| Configuration fingerprint | `hashlib` | SHA-256 | tamper evidence, not a secret |
| Random identifiers / tokens | `secrets`, `uuid4`, `gen_random_uuid()`, Web Crypto (`crypto.randomUUID`) | CSPRNG | `random.Random` is used **only** for synthetic vitals/ECG in `app/services/simulation.py` |
| Transport | Vercel / Supabase (TLS 1.2+), `httpx` (certifi CA bundle, `verify=True`), libpq `sslmode=verify-full` | TLS | no code disables verification |

Banned (tests fail): `python-jose`, `pycrypto`/`Crypto`, `simplecrypt`, `crypto-js` and similar polyfills,
`hashlib.md5/sha1`, ECB mode, DES/RC4, `algorithms=None`, `verify=False`, `CERT_NONE`, `NODE_TLS_REJECT_UNAUTHORIZED`.
If field-level encryption is ever needed use `cryptography`'s AES-256-GCM with a random 96-bit nonce per message.

## 5. Certificate validation (T175)

The API's only outbound HTTP destination is the configured Supabase project (`httpx.AsyncClient(base_url=<SUPABASE_URL>,
verify=True)`); Postgres connections require `verify-full`. Proxy interception check (manual, before go-live): route the
API through mitmproxy with its untrusted CA (`HTTPS_PROXY=...`); calls to Supabase must fail with a certificate error
and the database connection must refuse the proxy certificate. `test_secure_config.py::test_t175_rejects_bad_certificates`
runs the badssl.com checks when `RUN_NETWORK_TESTS=1` (scheduled CI job).

## 6. Dynamic code loading (T305)

* Frontend: Vite bundles all code; `import()` is used only with static paths (route code-splitting, same-origin
  chunks). No `eval`, `new Function`, remote `<script src>` or CDN-hosted libraries (tests grep `frontend/src`,
  `index.html` and `dist/`). The Content-Security-Policy `script-src 'self'` header is set by the web front-end
  configuration (`frontend/vercel.json` / `index.html`, owned by the front-end agent).
* Backend: no `importlib`, `__import__`, `exec` or `eval`; simulation scenarios are an enum allow-list (unknown names
  return 422).

## 7. Third-party components (T241/T1364/T370)

| Component | Version policy | Purpose | License | Owner / notes |
|---|---|---|---|---|
| FastAPI, Starlette, Pydantic, pydantic-settings | exact pins in `backend/requirements.txt` | API framework, validation | MIT / BSD-3 | backend |
| PyJWT[crypto], cryptography | exact pins | token verification | MIT / Apache-2.0 OR BSD-3 | backend |
| psycopg, psycopg-pool | exact pins | Postgres driver | LGPL-3.0 (dynamic linking, unmodified: approved) | backend |
| httpx, uvicorn, email-validator, python-multipart | exact pins | HTTP client, ASGI server, validation, uploads | BSD-3 / Unlicense / Apache-2.0 | backend |
| React, React Router, @supabase/supabase-js | exact versions + `pnpm-lock.yaml` | SPA, auth/realtime client | MIT | frontend |
| Vite, Vitest, TypeScript, Testing Library, jsdom | exact versions (dev) | build and tests | MIT / Apache-2.0 | frontend |
| Supabase (Postgres, Auth, Storage, Realtime) | managed service | data layer | vendor terms (DPA) | approved processor |
| Vercel | managed service | hosting | vendor terms (DPA) | approved processor |

Rules:

* Before adding a dependency check maintenance activity, known vulnerabilities (OSV), license (allow-list: MIT, BSD,
  Apache-2.0, ISC, PSF, Unlicense, MPL-2.0; LGPL only for unmodified dynamically linked libraries; GPL/AGPL need
  review) and prefer what the stack already has. Record it in the table above in the same PR.
* Pins are exact (`==` / no `^`/`~`); `pnpm install --frozen-lockfile` in CI and on Vercel; installs only from
  pypi.org / registry.npmjs.org.
* CI (`.github/workflows/ci.yml`) runs `pip-audit --strict` and `pnpm audit --audit-level=moderate` on every push/PR
  and weekly, a scanner canary (a known-vulnerable pin must be detected), gitleaks secret scanning and license checks.
  Dependabot (`.github/dependabot.yml`) opens weekly update PRs for pip, npm and GitHub Actions.
* Least privilege for third parties: the browser holds only the anon key (RLS applies); the service role key exists only
  in the backend Vercel project; Vercel tokens in CI are project-scoped secrets.
* EOL: Python 3.12+ (supported until 2028-10), Node 20.19+/22 LTS; plan upgrades before end of support.

**Audit status (2026-11-12):** `pip-audit -r backend/requirements.txt` reported advisories in starlette 0.46.2,
python-multipart 0.0.20 and PyJWT 2.10.1; fixed by pinning fastapi 0.136.3 / starlette 1.3.1, python-multipart 0.0.31
and PyJWT 2.15.1 (FastAPI 0.137+ was not adopted because its router internals change the route inventory used by the
authorization guard). `pnpm audit`: no known vulnerabilities.
