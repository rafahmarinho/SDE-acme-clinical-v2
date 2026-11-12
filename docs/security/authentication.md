# Authentication

ACME Clinical uses **Supabase Auth** (email + password, TOTP MFA) as its account and identity
management system. The FastAPI backend never sees or stores passwords; it verifies Supabase access
tokens on every request and resolves role/activation from `public.staff_profiles`.

Evidence lives in `backend/tests/test_authentication.py` and `frontend/src/screens/auth.test.tsx`.

## Components and how each one authenticates

| From → to | Credential | Notes |
|---|---|---|
| Browser → Supabase Auth/REST/Realtime | anon key + user JWT | RLS on every table; anon key alone returns no clinical rows |
| Browser (SPA) → FastAPI | `Authorization: Bearer <Supabase access token>` | signature, `aud`, `iss`, `exp` verified (`app/core/security.py`); Origin, IP and `X-*` headers grant nothing |
| FastAPI → Supabase Auth Admin API | service role key (server env var only) | `httpx` with `verify=True`, `follow_redirects=False` (`routers/staff.py: supabase_admin_client`) |
| FastAPI → Postgres | `acme_api` role password + TLS (`sslmode=verify-full`) | least-privilege role; config refuses non-TLS DSNs |
| Operator CLI → Postgres | `ADMIN_DATABASE_URL` (operator role) + TLS | used only from a trusted workstation |
| Simulated monitor → bed binding | per-device pairing code (SHA-256 stored) | `public.verify_monitor_secret()` (throttled) |

There is **no static-secret machine endpoint** (`/internal/*`, cron): every API call carries a user
JWT, so there is no shared secret to brute force. Vercel functions cannot require client certificates;
signed JWTs and secrets over TLS are the chosen equivalent of mutual TLS.

The service role key, JWT secret and database URL are **never** exposed to the browser: the SPA only
reads `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` and `VITE_API_BASE_URL` (tested).

### Key rotation

* Supabase service role / secret API key: generate a new secret key in the Supabase dashboard, update
  `SUPABASE_SERVICE_ROLE_KEY` in the Vercel API project, redeploy, then revoke the old key.
* JWT signing: rotate in Supabase (JWT keys); update `SUPABASE_JWT_SECRET` on the API, redeploy.
  Existing sessions must sign in again.
* `acme_api` password: `alter role acme_api password '<new>'` as the migration owner, update
  `DATABASE_URL` on Vercel, redeploy. Generate secrets with `openssl rand -base64 32`.
* Monitor pairing codes: `python -m app.cli provision-monitor-secrets` (old codes stop working).

`app.services.passwords.system_secret_problems()` / `database_url_problems()` reject placeholder,
short or low-entropy system credentials and superuser DSNs (the `.env.example` placeholders fail).

## Passwords

* Stored only by Supabase Auth as salted **bcrypt** hashes (`auth.users.encrypted_password`). No table
  created by our migrations has a password column; `seed.sql` never writes to the `auth` schema and
  contains no `crypt()`/`gen_salt()` (tested).
* Policy (`backend/app/services/passwords.py`, mirrored in `frontend/src/lib/authPolicy.ts`):
  12–128 characters (minimum configurable by administrators in Settings → Security,
  `security_settings.password_min_length`, never below 12), lower-case + upper-case + digit, no common,
  repeated or sequential values, no name/e-mail/service words.
* Platform floor in `supabase/config.toml`: `minimum_password_length = 12`,
  `password_requirements = "lower_upper_letters_digits"`. **Leaked-password protection** must be
  switched on in the hosted project (Authentication → Attack Protection).
* Residual risk: password updates go from the browser straight to Supabase Auth, so a configured
  minimum above 12 is enforced by the UI; Supabase enforces the 12-character floor for any client.
* Password inputs use `PasswordField` only: masked by default, explicit "Show" toggle that re-masks on
  blur, `autocomplete="current-password"`/`"new-password"`, spellcheck off.

### Change and recovery

* **Change password** (`/reset-password` while signed in): the current password is required and is
  verified with a throw-away, non-persistent Supabase client (so the signed-in session and its MFA
  level are untouched) before `updateUser({ password, current_password })`. `secure_password_change`
  adds reauthentication for sessions older than 24 h. All sessions are signed out afterwards.
* **Recovery** (`/forgot-password`): always shows the same neutral message and sets no cookie or storage
  that differs by input (also when Supabase throws); Supabase e-mails a single-use link valid for
  **15 minutes** (`otp_expiry = 900`), at most one per address per minute (`max_frequency`) and 10 per hour
  per project (`email_sent`). No temporary passwords, no security questions (the PRD flow uses e-mail links;
  the link plus lockout and rate limits replace steps 3-4 of the SD Elements sequence), no personal
  image/phrase. Redirects are restricted to an exact allow-list. After the new password is set every
  session on every device is signed out (`signOut({ scope: "global" })`, stronger than an opt-in), and the
  **password changed** notification e-mail (`supabase/templates/password_changed.html`, never containing the
  password) is sent by Supabase Auth.

### Anti-automation on recovery (T2) - open decision

SD Elements T2 asks for a CAPTCHA (with an accessible alternative) on the reset form. Supabase Auth only
supports Turnstile or hCaptcha, both of which load a third-party script and iframe from the provider's origin;
the SPA's CSP (`script-src 'self'`, `frame-src 'none'`) and T279 (no third-party CDN scripts) forbid that, and
enabling `[auth.captcha]` would also require a token on every sign-in and password re-verification. CAPTCHA is
therefore **not** enabled. Compensating controls: Supabase per-IP limits (`token_verifications`,
`sign_in_sign_ups`), per-address `max_frequency = 60s`, the project-wide `email_sent = 10/h`, the per-account
lockout hook, uniform responses and Vercel Firewall rate limits (deployment.md). To close the gap the security
owner must either accept this residual risk in writing or approve the CSP exception for
`https://challenges.cloudflare.com` (script-src + frame-src) and the Turnstile widget on Login, ForgotPassword,
StepUpDialog and the re-authentication helper.

## Sign-in, errors and throttling

* Every sign-in failure shows **"Invalid email or password."** (unknown e-mail, wrong password, locked,
  unconfirmed, banned, rate limited). The API returns the same 401 body for every token failure.
* **Lockout**: the Supabase *password verification attempt* hook
  (`public.hook_password_verification_attempt`, migration `0006_auth.sql`) counts consecutive failures per
  account; after `lockout_threshold` failures the account is locked for `lockout_minutes`, doubling on
  repeated lock-outs (max 8×). While locked even the right password is refused with the generic text.
  Administrators can unlock (`POST /v1/staff/{id}/unlock`, audited). A soft lock never lifts a ban.
  Enable the hook in the hosted project (Authentication → Hooks); it requires a plan that offers it.
* Rate limits (`[auth.rate_limit]`): 10 sign-in/sign-up and 10 OTP/recovery verifications per 5 minutes
  per IP, 10 e-mails per hour. The API also rate-limits `/v1/auth/*`.
* Random client-side delays are **not** a defence and are not used. App-owned identity endpoints (staff
  invitation) use a uniform minimum duration with `secrets` jitter (`uniform_auth_timing`); the
  Supabase login endpoint relies on its rate limits and the lockout hook. Timing of the hosted login
  endpoint should be measured per release (valid vs unknown e-mails) and reported to Supabase if it
  differs beyond noise.
* CAPTCHA is not enabled yet (needs a Turnstile/hCaptcha widget and a CSP change); tracked as residual risk.

## Multi-factor authentication

TOTP is enabled (`[auth.mfa.totp]`). Administrators must use it: `get_principal` rejects admin tokens
below `aal2`. After the password step the Login screen asks for the code when the account has a
verified factor, or starts enrolment (QR code + manual key) when the API requires MFA. A lost factor is
removed by another administrator through the Supabase dashboard/Admin API (audited); no security
questions. Other roles may enrol voluntarily.

## Accounts and identities

* No self sign-up (`enable_signup = false`), no anonymous sign-ins. Accounts are created only by
  administrators (Team → Invite): Supabase e-mails a single-use invitation link; the person sets their
  own password. The invite response is identical whether or not the address already exists; duplicate
  attempts are audit-logged (`staff.invite_duplicate`) for administrator review.
* **One person = one account**: `staff_profiles.user_id` is the `auth.users` primary key; e-mails are
  unique (`citext`). Accounts are personal — never shared — and no seed creates role-named accounts.
  Every clinical action records the individual user id.
* **One username rule** (API `canonical_email`, UI `canonicalEmail`, DB constraint
  `staff_profiles_email_canonical`): ASCII e-mail, stored lower-case; the UI trims; inner whitespace and
  invisible characters are rejected. Authorization always keys on the UUID, never on the e-mail text.
* Lifecycle: invite, change role, change wards, deactivate (profile `is_active = false` **and** a
  Supabase ban, so sign-in and token refresh stop), reactivate (ban lifted), unlock. Admins cannot
  change their own role or deactivate themselves. All changes are audited. Account review: the Team
  screen lists every person with role, wards, status and last sign-in.
* E-mail changes require confirmation from both addresses (`double_confirm_changes = true`).

## Default accounts

`supabase/seed.sql` seeds demo patients and monitors only — no accounts, no passwords, no device
secrets in clear. Demo staff come from `python -m app.cli create-demo-staff` (refuses `APP_ENV=production`
unless `--allow-demo`): one named, personal account per role, unique random password printed once.
Deactivate demo accounts after a demo. Never use the local `supabase start` demo keys outside local
development.

## Previous-login notice

The hook records every attempt in `private.login_attempts` (90-day retention, not exposed through the
Data API). `public.login_activity_summary(user)` returns the failed attempts since the previous successful
sign-in for the caller only; the API's `POST /v1/auth/session` returns the previous sign-in time and IP
and shows them after login.

## Monitor authenticity

Each monitor has a per-device pairing code; only its SHA-256 is stored. `public.verify_monitor_secret()`
compares hashes, refuses retired monitors and throttles failures in the database (shared across all
API instances, T70): 5 failures lock verification for 15 minutes and every further failure after a lock
doubles it (30 min, 1 h, 2 h ...) up to **24 hours** (`0012_device_auth_lockout.sql`). The response is the
same for a wrong code, an unknown monitor and a locked monitor. Each failure is audited
(`monitor.auth_failed`), a lockout is audited (`monitor.auth_locked`) and raises a `device_auth_lockout`
admin alert; administrators lift it with `DELETE /v1/monitors/{id}/auth-lockout` (settings:manage,
audited `monitor.auth_unlocked`). Pairing attempts are also rate-limited per client (10/min) and per source
IP (20/min) in `backend/app/core/middleware.py`. Codes are issued by `provision-monitor-secrets` and never logged or
returned by the API. Future real monitors must present manufacturer-backed identity (device
certificate) at registration.

## Hosted-project checklist

- [ ] Authentication → Providers → Email: confirm email ON, secure password change ON, double confirm ON, sign-ups OFF
- [ ] Attack Protection: leaked-password protection ON, minimum length 12, lower/upper/digits
- [ ] MFA: TOTP enabled
- [ ] Hooks: Password Verification Attempt → `public.hook_password_verification_attempt`
- [ ] Rate limits as in `supabase/config.toml`; URL configuration: site URL + exact redirect URLs
- [ ] Anonymous sign-ins OFF; no installation/bootstrap accounts left with default credentials
- [ ] Email: OTP / link expiry 900 s; templates from `supabase/templates/` (invite, recovery, e-mail change,
      reauthentication) and the security notifications "password changed" and "e-mail changed" enabled
      (the `deploy` job runs `supabase config push`; verify in Authentication → Emails)
- [ ] SMTP: custom provider configured with STARTTLS on 587 (see deployment.md "Transactional e-mail")
- [ ] Manual check per release: a recovery link used twice, or after 15 minutes, is rejected; the
      "password changed" e-mail arrives and contains no password
