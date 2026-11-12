# Authorization

ACME Clinical enforces authorization on the server in two layers that share one definition:

1. **API (FastAPI)**: `backend/app/core/security.py` is the only module that defines roles, permissions,
   the role-to-permission matrix, the public and self-service whitelists, `require()` / `require_any()` /
   `require_recent_auth()` dependencies and the 404 helper `not_found()`. Routers never compare role strings.
2. **Database (Supabase PostgreSQL)**: row-level security is enabled and forced on every table. Policies call
   shared helpers (`public.has_permission()`, `public.can_access_patient()`, `public.can_access_ward()`,
   `public.can_configure_thresholds()`). `public.role_permissions` holds the same matrix as the Python code
   (`supabase/migrations/0003_authz_rbac.sql`); `backend/tests/test_database_policies.py` fails if they differ.

Frontend navigation (React) only adapts the UI to the permissions returned by `GET /v1/me`. It is never an
enforcement point.

## Permission matrix

| Permission | Nurse | Physician | Biomed tech | Admin | Used by |
|---|:-:|:-:|:-:|:-:|---|
| `patient:read` | yes | yes | | yes | patient list/detail/readings, observations list, files list/URL |
| `observation:write` | yes | yes | | | record observations |
| `alarm:read` | yes | yes | yes | yes | alarms, wards overview, thresholds list |
| `alarm:ack` | yes | yes | | | acknowledge alarms |
| `threshold:write` | | yes | | | ward/patient alarm limits (own wards only) |
| `device:read` | yes | yes | yes | yes | monitors list |
| `device:write` | | | yes | yes | bind/unbind monitors |
| `maintenance:read` | | | yes | yes | maintenance history |
| `maintenance:write` | | | yes | | maintenance records |
| `report:read` | | yes | | yes | ward activity report |
| `file:write` | yes | yes | | | upload attachments |
| `break_glass:request` | yes | yes | | | emergency access |
| `break_glass:review` | | | | yes | review/revoke emergency access |
| `staff:manage` | | | | yes | team management |
| `settings:manage` | | | | yes | security settings |
| `simulation:control` | | | | yes | scenario, advance, reset |
| `events:read_all` | | | | yes | audit integrity check, all events |

Object scope on top of permissions (RLS): nurses and physicians see patients of their assigned wards only
(plus a patient covered by an active break-glass grant); administrators see all wards; biomedical technicians
see devices, wards and alarms but no clinical notes. Objects outside the caller's scope return **404**, the
same response as a nonexistent id, and every object key is a UUID path parameter.

Identity and role come only from the verified Supabase JWT `sub` and the `staff_profiles` row loaded on
every request. Token claims such as `role`, `app_metadata`, `user_metadata`, request headers (`X-Role`) or
body fields (`role`, `is_admin`, `author_id`, `user_id`) never influence authorization. Deactivation and
role changes take effect on the next request.

## Separation of duties

Duty areas: **authorization** (granting roles), **custody** (devices/monitors), **recording** (observations,
alarm acknowledgements, audit trail) and **verification** (audit and break-glass review).

* Static: no role holds a conflicting pair (`CONFLICTING_PERMISSIONS` in `security.py`, tested):
  administrators do not record observations, acknowledge alarms, change alarm limits or use break-glass;
  clinicians cannot manage accounts; biomedical technicians cannot acknowledge alarms or change limits;
  break-glass users cannot review break-glass.
* Dynamic (database-enforced, `staff_profiles_guard` trigger):
  * nobody can change their own role or activation;
  * accounts cannot be created as administrators through the API;
  * granting the administrator role requires an approved `staff_role_requests` row decided by a second
    administrator (not the requester, not the target) within the last hour, and that approver applies it.
* Break-glass reviews must be done by an administrator other than the requester (API check, RLS policy and
  `CHECK (reviewed_by <> user_id)`).
* The audit log (`public.events`) is append-only for every role (no UPDATE/DELETE grants plus a blocking
  trigger) and hash-chained.

## Highly sensitive transactions (step-up)

`require_recent_auth(*perms, max_age=...)` requires the permission **and** a recent primary authentication
(latest `amr` timestamp in the Supabase JWT). Otherwise the API answers `401` with
`WWW-Authenticate: Bearer error="insufficient_user_authentication", error_description="step_up_required"`,
records `authz.step_up_required`, and the SPA asks for the password again and retries.

| Action | Window |
|---|---|
| Staff invitation, role/activation change (`/v1/staff`) | 5 minutes |
| Simulation reset (`POST /v1/simulation/reset`) | 5 minutes |
| Security settings change (`PATCH /v1/settings/security`) | 5 minutes |
| Alarm-limit changes (`PUT /v1/thresholds/...`) | 5 minutes |
| Break-glass activation (`POST /v1/break-glass`) | 15 minutes |

Administrators additionally need `aal2` (MFA) on every request when `require_mfa_for_admin` is on.
Alarm-limit plausibility is validated server-side and every change is audited with old and new values.

## Break-glass procedure

1. A nurse or physician who must treat a patient outside their wards opens the emergency-access dialog,
   accepts the warning (`acknowledged_warning: true` is required by the API) and enters a reason
   (10 to 500 characters). If the last sign-in is older than 15 minutes they re-enter their password.
2. `POST /v1/break-glass` creates a grant for that single patient, valid for **30 minutes** (database
   maximum 4 hours). It is a separate row, not a role change.
3. While the grant is active and not revoked, RLS lets the user read that patient, its readings, alarms,
   observations and files, record observations and acknowledge alarms. Alarm-limit changes, staff
   management, device management and simulation control are never available through a grant.
4. Actions on the patient under a grant are audited as `break_glass.used` with the grant id
   (`record_break_glass_use()`); activation (`break_glass.granted`), revocation and review are audited too.
5. Access ends automatically at expiry, or earlier with `POST /v1/break-glass/{id}/revoke` (requester for
   their own grant, an administrator for anyone else's). `GET /v1/break-glass/mine` lists active grants.
6. An administrator who is not the requester reviews every grant via `GET /v1/break-glass/pending` and
   `POST /v1/break-glass/{id}/review` with `{"outcome": "appropriate" | "inappropriate"}`. Inappropriate use is
   handled by the clinical governance process.

## Unauthenticated routes

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/health` | Returns `{"status": "ok"}` only; no version, DB or environment details. |

Login, logout, password recovery and MFA are performed by Supabase Auth from the browser; the SPA's public
screens are `/login`, `/forgot-password` and `/reset-password`. `/docs` and `/openapi.json` exist only outside
production. Every other route requires a valid bearer token; routes that need no role permission are listed in
`SELF_SERVICE_ROUTES` (own session/profile, read-only views scoped by RLS). `assert_routes_protected(app)` fails
startup if a route has no authentication dependency or, outside that list, no permission dependency;
`backend/tests/test_authorization.py` checks the same and calls every protected route without valid credentials.
Changes to `PUBLIC_ROUTES` or `SELF_SERVICE_ROUTES` need a security review.

## Database accounts

| Account | Login | Purpose |
|---|---|---|
| `acme_api` | yes | FastAPI request handling. No direct grants; inherits `acme_api_rw`. `NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB`, owns nothing. |
| `acme_api_rw` | no | Group role with the API's table, column and function privileges. No TRUNCATE/DDL; DELETE only on ward assignments; audit events insert-only. |
| `acme_reset_owner` | no | Owns `public.reset_simulation_data()`, the only bulk-delete path (readings, alarms, observations); the function checks `simulation:control`. |
| `acme_reporting` | no | Read-only aggregates for reporting. |
| `authenticated` | Supabase | Browser sessions: read-only Realtime feeds filtered by RLS. |
| `anon` | Supabase | No access to any table, sequence or function. |
| `postgres` / `service_role` | - | Migrations and the admin-only invitation call; never used for request data access. |

The `acme_api` password is set out-of-band (`ALTER ROLE acme_api PASSWORD ...` in the SQL editor) and stored
only in the Vercel environment (`DATABASE_URL`). After deployment, check `\du+`,
`information_schema.role_table_grants` and `pg_policies` on the hosted project and record the result.
