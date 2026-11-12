<!-- SDE-SECURITY-HARDENING-START -->
## Security Hardening Execution Contract

This repository is a **placeholder scaffold** for ACME Clinical generated from `specs/PRD.md`. There is no production code yet. Every feature must be implemented following the per-countermeasure task recipes indexed below. Each recipe quotes the PRD text that introduces the feature, describes the naive approach the spec implies, and gives the secure pattern and checkable success criteria.

Rules for agents implementing this repository:
- Read the relevant `skills/<domain>/<ID>-<slug>/SKILL.md` **before** implementing the feature it covers.
- Implement in place in the scaffold files (`backend/`, `frontend/`, `supabase/`); do not create `*_secure.*` copies.
- After implementing a countermeasure, set `**Status:**` in its SKILL.md (Pending → Applied) and update the matching row below.
- Secrets only come from environment variables (`backend/.env.example`, `frontend/.env.example`); the Supabase service role key is server-only.

## Project Overview
| Property | Value |
|----------|-------|
| Application | acme-clinical-v2 (ACME Clinical) |
| SD Elements Project | [ACME Clinical v2](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/) |
| Project ID | 32 |
| Business Unit / Application | Afrika & SC - Labs (9) / ACME Clinical v2 (19) |
| Risk Policy | On-Boarding Policy (1) |
| Total Countermeasures | 334 (316 file-tracked + 18 PROCESS note-only) |
| Source | Spec files (specs/PRD.md) |
| Architecture | FastAPI + Pydantic API (`backend/`), React + Vite + TypeScript SPA with pnpm (`frontend/`), Supabase PostgreSQL/Auth/Storage/Realtime (`supabase/`), deployed separately on Vercel |

## Countermeasure Summary by Category

| Category | Count | Description |
|----------|-------|-------------|
| CODE_FIX | 234 | Secure implementation needed in application code, SQL migrations, security tests or repo config |
| INFRA | 82 | External infrastructure (Vercel / Supabase platform settings, cloud/org IT) |
| **FILE-TRACKED TOTAL** | **316** | Countermeasures with local skill files |

> **PROCESS countermeasures (18) are noted in SD Elements only, not tracked locally:** T2331, T380, T4594, T605, T2162, T2160, T454, T195, T176, T2356, T753, T2166, T453, T750, T2324, T756, T757, T2165.

## Skill Files

| Domain | Countermeasures | Category |
|--------|----------------|----------|
| authentication | 38 | CODE_FIX |
| session-management | 23 | CODE_FIX |
| authorization | 22 | CODE_FIX |
| api-security | 8 | CODE_FIX |
| input-validation | 30 | CODE_FIX |
| web-frontend-security | 31 | CODE_FIX |
| logging-audit | 16 | CODE_FIX |
| file-handling | 14 | CODE_FIX |
| clinical-safety-resilience | 11 | CODE_FIX |
| privacy | 16 | CODE_FIX |
| secure-config-supply-chain | 19 | CODE_FIX |
| database | 6 | CODE_FIX |
| cloud-infrastructure | 55 | INFRA |
| database-infrastructure | 27 | INFRA |
| **Total** | **316** | |

## Countermeasure Index

### authentication (38)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T1 | Use multi-factor authentication for remote access to high risk systems or administrative access to services | [skills/authentication/T1-use-multi-factor-authentication-for-remote-access/SKILL.md](./skills/authentication/T1-use-multi-factor-authentication-for-remote-access/SKILL.md) | 5 | CODE_FIX | Pending |
| T3 | Require old passwords when users change passwords | [skills/authentication/T3-require-old-passwords-when-users-change-passwords/SKILL.md](./skills/authentication/T3-require-old-passwords-when-users-change-passwords/SKILL.md) | 6 | CODE_FIX | Pending |
| T4 | Use configurable password policies | [skills/authentication/T4-use-configurable-password-policies/SKILL.md](./skills/authentication/T4-use-configurable-password-policies/SKILL.md) | 5 | CODE_FIX | Pending |
| T5 | Use minimum standards for passwords | [skills/authentication/T5-use-minimum-standards-for-passwords/SKILL.md](./skills/authentication/T5-use-minimum-standards-for-passwords/SKILL.md) | 5 | CODE_FIX | Pending |
| T6 | Implement account lockout or authentication throttling | [skills/authentication/T6-implement-account-lockout-or-authentication-thrott/SKILL.md](./skills/authentication/T6-implement-account-lockout-or-authentication-thrott/SKILL.md) | 5 | CODE_FIX | Pending |
| T7 | Salt and hash stored passwords | [skills/authentication/T7-salt-and-hash-stored-passwords/SKILL.md](./skills/authentication/T7-salt-and-hash-stored-passwords/SKILL.md) | 6 | CODE_FIX | Pending |
| T8 | Use Consistent Error Handling for All Authentication Failures | [skills/authentication/T8-use-consistent-error-handling-for-all-authenticati/SKILL.md](./skills/authentication/T8-use-consistent-error-handling-for-all-authenticati/SKILL.md) | 5 | CODE_FIX | Pending |
| T10 | Use server-to-server authentication | [skills/authentication/T10-use-server-to-server-authentication/SKILL.md](./skills/authentication/T10-use-server-to-server-authentication/SKILL.md) | 6 | CODE_FIX | Pending |
| T12 | Mask User Passwords by Default | [skills/authentication/T12-mask-user-passwords-by-default/SKILL.md](./skills/authentication/T12-mask-user-passwords-by-default/SKILL.md) | 2 | CODE_FIX | Pending |
| T61 | Disable default accounts or change all default passwords | [skills/authentication/T61-disable-default-accounts-or-change-all-default-pas/SKILL.md](./skills/authentication/T61-disable-default-accounts-or-change-all-default-pas/SKILL.md) | 9 | CODE_FIX | Pending |
| T73 | Use random delays in authentication failures | [skills/authentication/T73-use-random-delays-in-authentication-failures/SKILL.md](./skills/authentication/T73-use-random-delays-in-authentication-failures/SKILL.md) | 5 | CODE_FIX | Pending |
| T77 | Test for single-factor authentication | [skills/authentication/T77-test-for-single-factor-authentication/SKILL.md](./skills/authentication/T77-test-for-single-factor-authentication/SKILL.md) | 5 | CODE_FIX | Pending |
| T78 | Test strength of password reset mechanism | [skills/authentication/T78-test-strength-of-password-reset-mechanism/SKILL.md](./skills/authentication/T78-test-strength-of-password-reset-mechanism/SKILL.md) | 9 | CODE_FIX | Pending |
| T79 | Test password change functions | [skills/authentication/T79-test-password-change-functions/SKILL.md](./skills/authentication/T79-test-password-change-functions/SKILL.md) | 6 | CODE_FIX | Pending |
| T80 | Test password requirements | [skills/authentication/T80-test-password-requirements/SKILL.md](./skills/authentication/T80-test-password-requirements/SKILL.md) | 5 | CODE_FIX | Pending |
| T81 | Test account lockout | [skills/authentication/T81-test-account-lockout/SKILL.md](./skills/authentication/T81-test-account-lockout/SKILL.md) | 5 | CODE_FIX | Pending |
| T82 | Test authentication error consistency | [skills/authentication/T82-test-authentication-error-consistency/SKILL.md](./skills/authentication/T82-test-authentication-error-consistency/SKILL.md) | 5 | CODE_FIX | Pending |
| T114 | Test system-to-system authentication lockout or throttling | [skills/authentication/T114-test-system-to-system-authentication-lockout-or-thr/SKILL.md](./skills/authentication/T114-test-system-to-system-authentication-lockout-or-thr/SKILL.md) | 8 | CODE_FIX | Pending |
| T124 | Test for authentication timing vulnerability | [skills/authentication/T124-test-for-authentication-timing-vulnerability/SKILL.md](./skills/authentication/T124-test-for-authentication-timing-vulnerability/SKILL.md) | 5 | CODE_FIX | Pending |
| T135 | Assign each person using the system a unique user ID | [skills/authentication/T135-assign-each-person-using-the-system-a-unique-user/SKILL.md](./skills/authentication/T135-assign-each-person-using-the-system-a-unique-user/SKILL.md) | 5 | CODE_FIX | Pending |
| T220 | Verify that user password is salted and hashed | [skills/authentication/T220-verify-that-user-password-is-salted-and-hashed/SKILL.md](./skills/authentication/T220-verify-that-user-password-is-salted-and-hashed/SKILL.md) | 6 | CODE_FIX | Pending |
| T222 | Verify server-to-server authentication | [skills/authentication/T222-verify-server-to-server-authentication/SKILL.md](./skills/authentication/T222-verify-server-to-server-authentication/SKILL.md) | 6 | CODE_FIX | Pending |
| T225 | Test that password fields are masked by default | [skills/authentication/T225-test-that-password-fields-are-masked-by-default/SKILL.md](./skills/authentication/T225-test-that-password-fields-are-masked-by-default/SKILL.md) | 2 | CODE_FIX | Pending |
| T230 | Test that server-to-server system accounts meet minimum password requirements | [skills/authentication/T230-test-that-server-to-server-system-accounts-meet-mi/SKILL.md](./skills/authentication/T230-test-that-server-to-server-system-accounts-meet-mi/SKILL.md) | 8 | CODE_FIX | Pending |
| T233 | Verify that each person using the system is assigned a unique user ID | [skills/authentication/T233-verify-that-each-person-using-the-system-is-assign/SKILL.md](./skills/authentication/T233-verify-that-each-person-using-the-system-is-assign/SKILL.md) | 5 | CODE_FIX | Pending |
| T286 | Make sure username rules are consistent among the registration system, authentication system, and application | [skills/authentication/T286-make-sure-username-rules-are-consistent-among-the/SKILL.md](./skills/authentication/T286-make-sure-username-rules-are-consistent-among-the/SKILL.md) | 5 | CODE_FIX | Pending |
| T287 | Test that usernames are handled consistently by registration system, authentication system and application | [skills/authentication/T287-test-that-usernames-are-handled-consistently-by-re/SKILL.md](./skills/authentication/T287-test-that-usernames-are-handled-consistently-by-re/SKILL.md) | 5 | CODE_FIX | Pending |
| T323 | Test that default accounts are disabled or default passwords are changed | [skills/authentication/T323-test-that-default-accounts-are-disabled-or-default/SKILL.md](./skills/authentication/T323-test-that-default-accounts-are-disabled-or-default/SKILL.md) | 9 | CODE_FIX | Pending |
| T340 | Use an account and identity management system | [skills/authentication/T340-use-an-account-and-identity-management-system/SKILL.md](./skills/authentication/T340-use-an-account-and-identity-management-system/SKILL.md) | 7 | CODE_FIX | Pending |
| T425 | Check the authenticity of external devices/applications | [skills/authentication/T425-check-the-authenticity-of-external-devices-applica/SKILL.md](./skills/authentication/T425-check-the-authenticity-of-external-devices-applica/SKILL.md) | 6 | CODE_FIX | Pending |
| T426 | Verify that the authenticity of external devices/applications is properly checked | [skills/authentication/T426-verify-that-the-authenticity-of-external-devices-a/SKILL.md](./skills/authentication/T426-verify-that-the-authenticity-of-external-devices-a/SKILL.md) | 6 | CODE_FIX | Pending |
| T427 | Implement previous login (access) notification | [skills/authentication/T427-implement-previous-login-access-notification/SKILL.md](./skills/authentication/T427-implement-previous-login-access-notification/SKILL.md) | 4 | CODE_FIX | Pending |
| T428 | Test that the system provides previous login (access) notifications | [skills/authentication/T428-test-that-the-system-provides-previous-login-acces/SKILL.md](./skills/authentication/T428-test-that-the-system-provides-previous-login-acces/SKILL.md) | 4 | CODE_FIX | Pending |
| T517 | Protect user registration and account modification pages against user enumeration | [skills/authentication/T517-protect-user-registration-and-account-modification/SKILL.md](./skills/authentication/T517-protect-user-registration-and-account-modification/SKILL.md) | 6 | CODE_FIX | Pending |
| T518 | Test that registration and account modification pages are protected against user enumeration | [skills/authentication/T518-test-that-registration-and-account-modification-pa/SKILL.md](./skills/authentication/T518-test-that-registration-and-account-modification-pa/SKILL.md) | 6 | CODE_FIX | Pending |
| T589 | Verify that all the components are authenticated explicitly | [skills/authentication/T589-verify-that-all-the-components-are-authenticated-e/SKILL.md](./skills/authentication/T589-verify-that-all-the-components-are-authenticated-e/SKILL.md) | 9 | CODE_FIX | Pending |
| T2270 | Test to confirm that password policies are configurable | [skills/authentication/T2270-test-to-confirm-that-password-policies-are-configu/SKILL.md](./skills/authentication/T2270-test-to-confirm-that-password-policies-are-configu/SKILL.md) | 5 | CODE_FIX | Pending |
| T2277 | Test to confirm the use of an account and identity management system | [skills/authentication/T2277-test-to-confirm-the-use-of-an-account-and-identity/SKILL.md](./skills/authentication/T2277-test-to-confirm-the-use-of-an-account-and-identity/SKILL.md) | 7 | CODE_FIX | Pending |

### session-management (23)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T22 | Set secure flags on session cookies | [skills/session-management/T22-set-secure-flags-on-session-cookies/SKILL.md](./skills/session-management/T22-set-secure-flags-on-session-cookies/SKILL.md) | 5 | CODE_FIX | Pending |
| T23 | Set HttpOnly flag on session cookies | [skills/session-management/T23-set-httponly-flag-on-session-cookies/SKILL.md](./skills/session-management/T23-set-httponly-flag-on-session-cookies/SKILL.md) | 4 | CODE_FIX | Pending |
| T24 | Enforce idle session timeout | [skills/session-management/T24-enforce-idle-session-timeout/SKILL.md](./skills/session-management/T24-enforce-idle-session-timeout/SKILL.md) | 3 | CODE_FIX | Pending |
| T25 | Enforce absolute session timeouts | [skills/session-management/T25-enforce-absolute-session-timeouts/SKILL.md](./skills/session-management/T25-enforce-absolute-session-timeouts/SKILL.md) | 3 | CODE_FIX | Pending |
| T26 | Expire sessions on logout | [skills/session-management/T26-expire-sessions-on-logout/SKILL.md](./skills/session-management/T26-expire-sessions-on-logout/SKILL.md) | 6 | CODE_FIX | Pending |
| T27 | Turn off session rewriting | [skills/session-management/T27-turn-off-session-rewriting/SKILL.md](./skills/session-management/T27-turn-off-session-rewriting/SKILL.md) | 6 | CODE_FIX | Pending |
| T28 | Avoid 'Remember Me' features | [skills/session-management/T28-avoid-remember-me-features/SKILL.md](./skills/session-management/T28-avoid-remember-me-features/SKILL.md) | 4 | CODE_FIX | Pending |
| T86 | Test session ID uniqueness and rotation after authentication | [skills/session-management/T86-test-session-id-uniqueness-and-rotation-after-auth/SKILL.md](./skills/session-management/T86-test-session-id-uniqueness-and-rotation-after-auth/SKILL.md) | 9 | CODE_FIX | Pending |
| T88 | Test that secure flag is set on session cookie | [skills/session-management/T88-test-that-secure-flag-is-set-on-session-cookie/SKILL.md](./skills/session-management/T88-test-that-secure-flag-is-set-on-session-cookie/SKILL.md) | 5 | CODE_FIX | Pending |
| T90 | Test idle session timeout | [skills/session-management/T90-test-idle-session-timeout/SKILL.md](./skills/session-management/T90-test-idle-session-timeout/SKILL.md) | 3 | CODE_FIX | Pending |
| T91 | Test that HttpOnly flag is set on session cookie | [skills/session-management/T91-test-that-httponly-flag-is-set-on-session-cookie/SKILL.md](./skills/session-management/T91-test-that-httponly-flag-is-set-on-session-cookie/SKILL.md) | 4 | CODE_FIX | Pending |
| T92 | Test absolute session timeout | [skills/session-management/T92-test-absolute-session-timeout/SKILL.md](./skills/session-management/T92-test-absolute-session-timeout/SKILL.md) | 3 | CODE_FIX | Pending |
| T93 | Test that sessions expire upon logout | [skills/session-management/T93-test-that-sessions-expire-upon-logout/SKILL.md](./skills/session-management/T93-test-that-sessions-expire-upon-logout/SKILL.md) | 6 | CODE_FIX | Pending |
| T94 | Test that session IDs are not leaked through URLs | [skills/session-management/T94-test-that-session-ids-are-not-leaked-through-urls/SKILL.md](./skills/session-management/T94-test-that-session-ids-are-not-leaked-through-urls/SKILL.md) | 6 | CODE_FIX | Pending |
| T95 | Test for the absence of 'Remember Me' features | [skills/session-management/T95-test-for-the-absence-of-remember-me-features/SKILL.md](./skills/session-management/T95-test-for-the-absence-of-remember-me-features/SKILL.md) | 4 | CODE_FIX | Pending |
| T404 | Avoid setting broad paths and domains on session cookies | [skills/session-management/T404-avoid-setting-broad-paths-and-domains-on-session-c/SKILL.md](./skills/session-management/T404-avoid-setting-broad-paths-and-domains-on-session-c/SKILL.md) | 4 | CODE_FIX | Pending |
| T405 | Verify that broad paths and domains are not set on session cookies | [skills/session-management/T405-verify-that-broad-paths-and-domains-are-not-set-on/SKILL.md](./skills/session-management/T405-verify-that-broad-paths-and-domains-are-not-set-on/SKILL.md) | 4 | CODE_FIX | Pending |
| T429 | Limit the number of concurrent sessions for each account | [skills/session-management/T429-limit-the-number-of-concurrent-sessions-for-each-a/SKILL.md](./skills/session-management/T429-limit-the-number-of-concurrent-sessions-for-each-a/SKILL.md) | 4 | CODE_FIX | Pending |
| T430 | Test that the number of concurrent sessions for each account is limited | [skills/session-management/T430-test-that-the-number-of-concurrent-sessions-for-ea/SKILL.md](./skills/session-management/T430-test-that-the-number-of-concurrent-sessions-for-ea/SKILL.md) | 4 | CODE_FIX | Pending |
| T557 | Set SameSite attribute of cookies to Lax/Strict | [skills/session-management/T557-set-samesite-attribute-of-cookies-to-lax-strict/SKILL.md](./skills/session-management/T557-set-samesite-attribute-of-cookies-to-lax-strict/SKILL.md) | 5 | CODE_FIX | Pending |
| T1092 | Do not store sensitive cleartext information in cookies | [skills/session-management/T1092-do-not-store-sensitive-cleartext-information-in-co/SKILL.md](./skills/session-management/T1092-do-not-store-sensitive-cleartext-information-in-co/SKILL.md) | 4 | CODE_FIX | Pending |
| T1093 | Test that cookies do not contain sensitive cleartext information | [skills/session-management/T1093-test-that-cookies-do-not-contain-sensitive-clearte/SKILL.md](./skills/session-management/T1093-test-that-cookies-do-not-contain-sensitive-clearte/SKILL.md) | 4 | CODE_FIX | Pending |
| T1540 | Verify that browser data is cleared upon user logout | [skills/session-management/T1540-verify-that-browser-data-is-cleared-upon-user-logo/SKILL.md](./skills/session-management/T1540-verify-that-browser-data-is-cleared-upon-user-logo/SKILL.md) | 8 | CODE_FIX | Pending |

### authorization (22)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T9 | Implement authorization and screening for highly sensitive transactions | [skills/authorization/T9-implement-authorization-and-screening-for-highly-s/SKILL.md](./skills/authorization/T9-implement-authorization-and-screening-for-highly-s/SKILL.md) | 5 | CODE_FIX | Pending |
| T14 | Enforce the principle of least privilege | [skills/authorization/T14-enforce-the-principle-of-least-privilege/SKILL.md](./skills/authorization/T14-enforce-the-principle-of-least-privilege/SKILL.md) | 9 | CODE_FIX | Pending |
| T15 | Centralize authorization | [skills/authorization/T15-centralize-authorization/SKILL.md](./skills/authorization/T15-centralize-authorization/SKILL.md) | 9 | CODE_FIX | Pending |
| T16 | Authorize every non-public page | [skills/authorization/T16-authorize-every-non-public-page/SKILL.md](./skills/authorization/T16-authorize-every-non-public-page/SKILL.md) | 6 | CODE_FIX | Pending |
| T18 | Make authorization decisions using full context | [skills/authorization/T18-make-authorization-decisions-using-full-context/SKILL.md](./skills/authorization/T18-make-authorization-decisions-using-full-context/SKILL.md) | 9 | CODE_FIX | Pending |
| T83 | Verify transactional authorization and screening | [skills/authorization/T83-verify-transactional-authorization-and-screening/SKILL.md](./skills/authorization/T83-verify-transactional-authorization-and-screening/SKILL.md) | 5 | CODE_FIX | Pending |
| T84 | Test page-level authorization | [skills/authorization/T84-test-page-level-authorization/SKILL.md](./skills/authorization/T84-test-page-level-authorization/SKILL.md) | 6 | CODE_FIX | Pending |
| T85 | Test server-side enforcement of authorization | [skills/authorization/T85-test-server-side-enforcement-of-authorization/SKILL.md](./skills/authorization/T85-test-server-side-enforcement-of-authorization/SKILL.md) | 8 | CODE_FIX | Pending |
| T106 | Test that site is not vulnerable to direct object access attacks | [skills/authorization/T106-test-that-site-is-not-vulnerable-to-direct-object/SKILL.md](./skills/authorization/T106-test-that-site-is-not-vulnerable-to-direct-object/SKILL.md) | 8 | CODE_FIX | Pending |
| T128 | Test for access control bypass through user-controlled keys | [skills/authorization/T128-test-for-access-control-bypass-through-user-contro/SKILL.md](./skills/authorization/T128-test-for-access-control-bypass-through-user-contro/SKILL.md) | 8 | CODE_FIX | Pending |
| T226 | Verify that authorization is centralized | [skills/authorization/T226-verify-that-authorization-is-centralized/SKILL.md](./skills/authorization/T226-verify-that-authorization-is-centralized/SKILL.md) | 9 | CODE_FIX | Pending |
| T227 | Verify that application's access to database is restricted | [skills/authorization/T227-verify-that-application-s-access-to-database-is-re/SKILL.md](./skills/authorization/T227-verify-that-application-s-access-to-database-is-re/SKILL.md) | 8 | CODE_FIX | Pending |
| T337 | Include a 'break glass' feature that enables emergency functions | [skills/authorization/T337-include-a-break-glass-feature-that-enables-emergen/SKILL.md](./skills/authorization/T337-include-a-break-glass-feature-that-enables-emergen/SKILL.md) | 3 | CODE_FIX | Pending |
| T373 | Design and regulate access to unauthenticated parts of the application | [skills/authorization/T373-design-and-regulate-access-to-unauthenticated-part/SKILL.md](./skills/authorization/T373-design-and-regulate-access-to-unauthenticated-part/SKILL.md) | 8 | CODE_FIX | Pending |
| T381 | Test break-glass procedures | [skills/authorization/T381-test-break-glass-procedures/SKILL.md](./skills/authorization/T381-test-break-glass-procedures/SKILL.md) | 3 | CODE_FIX | Pending |
| T2141 | Perform function level authorization in API | [skills/authorization/T2141-perform-function-level-authorization-in-api/SKILL.md](./skills/authorization/T2141-perform-function-level-authorization-in-api/SKILL.md) | 8 | CODE_FIX | Pending |
| T2142 | Verify that function level authorization is implemented in API | [skills/authorization/T2142-verify-that-function-level-authorization-is-implem/SKILL.md](./skills/authorization/T2142-verify-that-function-level-authorization-is-implem/SKILL.md) | 8 | CODE_FIX | Pending |
| T2274 | Test to confirm that the principle of least privilege is strongly implemented | [skills/authorization/T2274-test-to-confirm-that-the-principle-of-least-privil/SKILL.md](./skills/authorization/T2274-test-to-confirm-that-the-principle-of-least-privil/SKILL.md) | 9 | CODE_FIX | Pending |
| T2276 | Test to confirm that authorization and authentication controls are in place for access to resources | [skills/authorization/T2276-test-to-confirm-that-authorization-and-authenticat/SKILL.md](./skills/authorization/T2276-test-to-confirm-that-authorization-and-authenticat/SKILL.md) | 7 | CODE_FIX | Pending |
| T2282 | Test to confirm that unauthenticated parts of the application are accessible | [skills/authorization/T2282-test-to-confirm-that-unauthenticated-parts-of-the/SKILL.md](./skills/authorization/T2282-test-to-confirm-that-unauthenticated-parts-of-the/SKILL.md) | 8 | CODE_FIX | Pending |
| T2388 | Enforce the principle of separation of duties | [skills/authorization/T2388-enforce-the-principle-of-separation-of-duties/SKILL.md](./skills/authorization/T2388-enforce-the-principle-of-separation-of-duties/SKILL.md) | 9 | CODE_FIX | Pending |
| T2393 | Verify the principle of Separation of Duties is strongly implemented | [skills/authorization/T2393-verify-the-principle-of-separation-of-duties-is-st/SKILL.md](./skills/authorization/T2393-verify-the-principle-of-separation-of-duties-is-st/SKILL.md) | 9 | CODE_FIX | Pending |

### api-security (8)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T65 | Restrict accepted HTTP verbs | [skills/api-security/T65-restrict-accepted-http-verbs/SKILL.md](./skills/api-security/T65-restrict-accepted-http-verbs/SKILL.md) | 6 | CODE_FIX | Pending |
| T113 | Test that site is not vulnerable to HTTP verb tampering | [skills/api-security/T113-test-that-site-is-not-vulnerable-to-http-verb-tamp/SKILL.md](./skills/api-security/T113-test-that-site-is-not-vulnerable-to-http-verb-tamp/SKILL.md) | 6 | CODE_FIX | Pending |
| T167 | Test that the application is not vulnerable to JSON Hijacking | [skills/api-security/T167-test-that-the-application-is-not-vulnerable-to-jso/SKILL.md](./skills/api-security/T167-test-that-the-application-is-not-vulnerable-to-jso/SKILL.md) | 7 | CODE_FIX | Pending |
| T228 | Test that application restricts HTTP message size | [skills/api-security/T228-test-that-application-restricts-http-message-size/SKILL.md](./skills/api-security/T228-test-that-application-restricts-http-message-size/SKILL.md) | 9 | CODE_FIX | Pending |
| T537 | Test that the size of incoming messages in services is restricted | [skills/api-security/T537-test-that-the-size-of-incoming-messages-in-service/SKILL.md](./skills/api-security/T537-test-that-the-size-of-incoming-messages-in-service/SKILL.md) | 8 | CODE_FIX | Pending |
| T1363 | Verify if message throttling is properly performed in Web APIs | [skills/api-security/T1363-verify-if-message-throttling-is-properly-performed/SKILL.md](./skills/api-security/T1363-verify-if-message-throttling-is-properly-performed/SKILL.md) | 8 | CODE_FIX | Pending |
| T1542 | Use the correct HTTP methods for making state-changing operations | [skills/api-security/T1542-use-the-correct-http-methods-for-making-state-chan/SKILL.md](./skills/api-security/T1542-use-the-correct-http-methods-for-making-state-chan/SKILL.md) | 7 | CODE_FIX | Pending |
| T2140 | Test that APIs do not expose sensitive information | [skills/api-security/T2140-test-that-apis-do-not-expose-sensitive-informatio/SKILL.md](./skills/api-security/T2140-test-that-apis-do-not-expose-sensitive-informatio/SKILL.md) | 7 | CODE_FIX | Pending |

### input-validation (30)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T11 | Disallow external redirects to unverified destinations | [skills/input-validation/T11-disallow-external-redirects-to-unverified-destinat/SKILL.md](./skills/input-validation/T11-disallow-external-redirects-to-unverified-destinat/SKILL.md) | 5 | CODE_FIX | Pending |
| T31 | Validate all forms of input | [skills/input-validation/T31-validate-all-forms-of-input/SKILL.md](./skills/input-validation/T31-validate-all-forms-of-input/SKILL.md) | 5 | CODE_FIX | Pending |
| T32 | Always perform input validation on a server | [skills/input-validation/T32-always-perform-input-validation-on-a-server/SKILL.md](./skills/input-validation/T32-always-perform-input-validation-on-a-server/SKILL.md) | 7 | CODE_FIX | Pending |
| T33 | Verify integrity of client-supplied read-only data | [skills/input-validation/T33-verify-integrity-of-client-supplied-read-only-data/SKILL.md](./skills/input-validation/T33-verify-integrity-of-client-supplied-read-only-data/SKILL.md) | 5 | CODE_FIX | Pending |
| T34 | Refuse overly-long, malformed, and non-printable characters unless required | [skills/input-validation/T34-refuse-overly-long-malformed-and-non-printable-cha/SKILL.md](./skills/input-validation/T34-refuse-overly-long-malformed-and-non-printable-cha/SKILL.md) | 5 | CODE_FIX | Pending |
| T39 | Refuse carriage returns and line feeds when adding data to HTTP response headers | [skills/input-validation/T39-refuse-carriage-returns-and-line-feeds-when-adding/SKILL.md](./skills/input-validation/T39-refuse-carriage-returns-and-line-feeds-when-adding/SKILL.md) | 4 | CODE_FIX | Pending |
| T74 | Avoid HTTP parameter pollution | [skills/input-validation/T74-avoid-http-parameter-pollution/SKILL.md](./skills/input-validation/T74-avoid-http-parameter-pollution/SKILL.md) | 5 | CODE_FIX | Pending |
| T89 | Test that site is not vulnerable to XSS | [skills/input-validation/T89-test-that-site-is-not-vulnerable-to-xss/SKILL.md](./skills/input-validation/T89-test-that-site-is-not-vulnerable-to-xss/SKILL.md) | 8 | CODE_FIX | Pending |
| T98 | Test for input validation on a server | [skills/input-validation/T98-test-for-input-validation-on-a-server/SKILL.md](./skills/input-validation/T98-test-for-input-validation-on-a-server/SKILL.md) | 7 | CODE_FIX | Pending |
| T99 | Test that clients cannot manipulate read-only data | [skills/input-validation/T99-test-that-clients-cannot-manipulate-read-only-data/SKILL.md](./skills/input-validation/T99-test-that-clients-cannot-manipulate-read-only-data/SKILL.md) | 5 | CODE_FIX | Pending |
| T101 | Test that application is not vulnerable to SQL injection | [skills/input-validation/T101-test-that-application-is-not-vulnerable-to-sql-inj/SKILL.md](./skills/input-validation/T101-test-that-application-is-not-vulnerable-to-sql-inj/SKILL.md) | 10 | CODE_FIX | Pending |
| T122 | Test for remote file include | [skills/input-validation/T122-test-for-remote-file-include/SKILL.md](./skills/input-validation/T122-test-for-remote-file-include/SKILL.md) | 10 | CODE_FIX | Pending |
| T125 | Test for open redirect | [skills/input-validation/T125-test-for-open-redirect/SKILL.md](./skills/input-validation/T125-test-for-open-redirect/SKILL.md) | 5 | CODE_FIX | Pending |
| T127 | Test for null byte injection | [skills/input-validation/T127-test-for-null-byte-injection/SKILL.md](./skills/input-validation/T127-test-for-null-byte-injection/SKILL.md) | 5 | CODE_FIX | Pending |
| T169 | Test that the site is not vulnerable to DOM-based XSS | [skills/input-validation/T169-test-that-the-site-is-not-vulnerable-to-dom-based/SKILL.md](./skills/input-validation/T169-test-that-the-site-is-not-vulnerable-to-dom-based/SKILL.md) | 8 | CODE_FIX | Pending |
| T420 | Prevent Client-Side Template Injection (CSTI) | [skills/input-validation/T420-prevent-client-side-template-injection-csti/SKILL.md](./skills/input-validation/T420-prevent-client-side-template-injection-csti/SKILL.md) | 6 | CODE_FIX | Pending |
| T421 | Verify if web page template is vulnerable to client side template injection (CSTI) | [skills/input-validation/T421-verify-if-web-page-template-is-vulnerable-to-clien/SKILL.md](./skills/input-validation/T421-verify-if-web-page-template-is-vulnerable-to-clien/SKILL.md) | 6 | CODE_FIX | Pending |
| T519 | Test that input validation is done on all forms of input | [skills/input-validation/T519-test-that-input-validation-is-done-on-all-forms-of/SKILL.md](./skills/input-validation/T519-test-that-input-validation-is-done-on-all-forms-of/SKILL.md) | 5 | CODE_FIX | Pending |
| T569 | Prevent parameter tampering in web services | [skills/input-validation/T569-prevent-parameter-tampering-in-web-services/SKILL.md](./skills/input-validation/T569-prevent-parameter-tampering-in-web-services/SKILL.md) | 5 | CODE_FIX | Pending |
| T577 | Verify that parameter tampering is prevented in web services | [skills/input-validation/T577-verify-that-parameter-tampering-is-prevented-in-we/SKILL.md](./skills/input-validation/T577-verify-that-parameter-tampering-is-prevented-in-we/SKILL.md) | 5 | CODE_FIX | Pending |
| T599 | Do not rely on mutable HTTP headers such as 'host' and 'referer' | [skills/input-validation/T599-do-not-rely-on-mutable-http-headers-such-as-host-a/SKILL.md](./skills/input-validation/T599-do-not-rely-on-mutable-http-headers-such-as-host-a/SKILL.md) | 4 | CODE_FIX | Pending |
| T600 | Verify that HTTP header values are not used without proper validation | [skills/input-validation/T600-verify-that-http-header-values-are-not-used-withou/SKILL.md](./skills/input-validation/T600-verify-that-http-header-values-are-not-used-withou/SKILL.md) | 4 | CODE_FIX | Pending |
| T1038 | Make homoglyphs distinguishable when showing them to users | [skills/input-validation/T1038-make-homoglyphs-distinguishable-when-showing-them/SKILL.md](./skills/input-validation/T1038-make-homoglyphs-distinguishable-when-showing-them/SKILL.md) | 5 | CODE_FIX | Pending |
| T1039 | Test that homoglyphs are distinguishable in the application's output | [skills/input-validation/T1039-test-that-homoglyphs-are-distinguishable-in-the-ap/SKILL.md](./skills/input-validation/T1039-test-that-homoglyphs-are-distinguishable-in-the-ap/SKILL.md) | 5 | CODE_FIX | Pending |
| T1145 | Verify if web page template is vulnerable to SSTI | [skills/input-validation/T1145-verify-if-web-page-template-is-vulnerable-to-ssti/SKILL.md](./skills/input-validation/T1145-verify-if-web-page-template-is-vulnerable-to-ssti/SKILL.md) | 8 | CODE_FIX | Pending |
| T1148 | Validate JSON files | [skills/input-validation/T1148-validate-json-files/SKILL.md](./skills/input-validation/T1148-validate-json-files/SKILL.md) | 6 | CODE_FIX | Pending |
| T1149 | Test if JSON files are validated against malicious inputs | [skills/input-validation/T1149-test-if-json-files-are-validated-against-malicious/SKILL.md](./skills/input-validation/T1149-test-if-json-files-are-validated-against-malicious/SKILL.md) | 6 | CODE_FIX | Pending |
| T1392 | Test for Server Side Request Forgery | [skills/input-validation/T1392-test-for-server-side-request-forgery/SKILL.md](./skills/input-validation/T1392-test-for-server-side-request-forgery/SKILL.md) | 8 | CODE_FIX | Pending |
| T2608 | Verify that the connection string is protected against connection string parameter pollution | [skills/input-validation/T2608-verify-that-the-connection-string-is-protected-aga/SKILL.md](./skills/input-validation/T2608-verify-that-the-connection-string-is-protected-aga/SKILL.md) | 9 | CODE_FIX | Pending |
| T2609 | Verify that the result set size returned by queries are controlled | [skills/input-validation/T2609-verify-that-the-result-set-size-returned-by-querie/SKILL.md](./skills/input-validation/T2609-verify-that-the-result-set-size-returned-by-querie/SKILL.md) | 7 | CODE_FIX | Pending |

### web-frontend-security (31)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T44 | Specify standard encoding format for all HTML content | [skills/web-frontend-security/T44-specify-standard-encoding-format-for-all-html-cont/SKILL.md](./skills/web-frontend-security/T44-specify-standard-encoding-format-for-all-html-cont/SKILL.md) | 4 | CODE_FIX | Pending |
| T63 | Disable auto-complete for confidential fields | [skills/web-frontend-security/T63-disable-auto-complete-for-confidential-fields/SKILL.md](./skills/web-frontend-security/T63-disable-auto-complete-for-confidential-fields/SKILL.md) | 3 | CODE_FIX | Pending |
| T64 | Set no-cache for confidential web pages | [skills/web-frontend-security/T64-set-no-cache-for-confidential-web-pages/SKILL.md](./skills/web-frontend-security/T64-set-no-cache-for-confidential-web-pages/SKILL.md) | 4 | CODE_FIX | Pending |
| T67 | Protect page navigation flow | [skills/web-frontend-security/T67-protect-page-navigation-flow/SKILL.md](./skills/web-frontend-security/T67-protect-page-navigation-flow/SKILL.md) | 5 | CODE_FIX | Pending |
| T96 | Test if your site is vulnerable to CSRF | [skills/web-frontend-security/T96-test-if-your-site-is-vulnerable-to-csrf/SKILL.md](./skills/web-frontend-security/T96-test-if-your-site-is-vulnerable-to-csrf/SKILL.md) | 7 | CODE_FIX | Pending |
| T111 | Test that your application turns off auto-complete for confidential data fields | [skills/web-frontend-security/T111-test-that-your-application-turns-off-auto-complete/SKILL.md](./skills/web-frontend-security/T111-test-that-your-application-turns-off-auto-complete/SKILL.md) | 3 | CODE_FIX | Pending |
| T112 | Test that site does not cache confidential pages | [skills/web-frontend-security/T112-test-that-site-does-not-cache-confidential-pages/SKILL.md](./skills/web-frontend-security/T112-test-that-site-does-not-cache-confidential-pages/SKILL.md) | 4 | CODE_FIX | Pending |
| T119 | Test for clickjacking | [skills/web-frontend-security/T119-test-for-clickjacking/SKILL.md](./skills/web-frontend-security/T119-test-for-clickjacking/SKILL.md) | 7 | CODE_FIX | Pending |
| T132 | Test for standard encoding format for all HTML content | [skills/web-frontend-security/T132-test-for-standard-encoding-format-for-all-html-con/SKILL.md](./skills/web-frontend-security/T132-test-for-standard-encoding-format-for-all-html-con/SKILL.md) | 4 | CODE_FIX | Pending |
| T142 | Test that the application's navigation flow is protected | [skills/web-frontend-security/T142-test-that-the-application-s-navigation-flow-is-pro/SKILL.md](./skills/web-frontend-security/T142-test-that-the-application-s-navigation-flow-is-pro/SKILL.md) | 5 | CODE_FIX | Pending |
| T219 | Avoid transmitting confidential data through URL parameters | [skills/web-frontend-security/T219-avoid-transmitting-confidential-data-through-url-p/SKILL.md](./skills/web-frontend-security/T219-avoid-transmitting-confidential-data-through-url-p/SKILL.md) | 6 | CODE_FIX | Pending |
| T258 | Secure web (cross domain) messaging in HTML5 | [skills/web-frontend-security/T258-secure-web-cross-domain-messaging-in-html5/SKILL.md](./skills/web-frontend-security/T258-secure-web-cross-domain-messaging-in-html5/SKILL.md) | 5 | CODE_FIX | Pending |
| T296 | Test that unencrypted confidential data is not stored without access control mechanisms | [skills/web-frontend-security/T296-test-that-unencrypted-confidential-data-is-not-sto/SKILL.md](./skills/web-frontend-security/T296-test-that-unencrypted-confidential-data-is-not-sto/SKILL.md) | 7 | CODE_FIX | Pending |
| T318 | Verify security of cross origin resource sharing (CORS) | [skills/web-frontend-security/T318-verify-security-of-cross-origin-resource-sharing-c/SKILL.md](./skills/web-frontend-security/T318-verify-security-of-cross-origin-resource-sharing-c/SKILL.md) | 8 | CODE_FIX | Pending |
| T319 | Verify that web messaging is securely used | [skills/web-frontend-security/T319-verify-that-web-messaging-is-securely-used/SKILL.md](./skills/web-frontend-security/T319-verify-that-web-messaging-is-securely-used/SKILL.md) | 5 | CODE_FIX | Pending |
| T322 | Include HTTP Strict-Transport-Security headers in HTTPS responses | [skills/web-frontend-security/T322-include-http-strict-transport-security-headers-in/SKILL.md](./skills/web-frontend-security/T322-include-http-strict-transport-security-headers-in/SKILL.md) | 5 | CODE_FIX | Pending |
| T325 | Use JavaScript Strict Mode | [skills/web-frontend-security/T325-use-javascript-strict-mode/SKILL.md](./skills/web-frontend-security/T325-use-javascript-strict-mode/SKILL.md) | 5 | CODE_FIX | Pending |
| T329 | Verify that JavaScript is used in Strict Mode | [skills/web-frontend-security/T329-verify-that-javascript-is-used-in-strict-mode/SKILL.md](./skills/web-frontend-security/T329-verify-that-javascript-is-used-in-strict-mode/SKILL.md) | 5 | CODE_FIX | Pending |
| T331 | Enforce policies through content security policy (CSP) or XSS protection headers | [skills/web-frontend-security/T331-enforce-policies-through-content-security-policy-c/SKILL.md](./skills/web-frontend-security/T331-enforce-policies-through-content-security-policy-c/SKILL.md) | 5 | CODE_FIX | Pending |
| T332 | Test that content security policy (CSP) headers are added | [skills/web-frontend-security/T332-test-that-content-security-policy-csp-headers-are/SKILL.md](./skills/web-frontend-security/T332-test-that-content-security-policy-csp-headers-are/SKILL.md) | 5 | CODE_FIX | Pending |
| T333 | Test that HTTP Strict-Transport-Security headers are sent in HTTPS responses | [skills/web-frontend-security/T333-test-that-http-strict-transport-security-headers-a/SKILL.md](./skills/web-frontend-security/T333-test-that-http-strict-transport-security-headers-a/SKILL.md) | 5 | CODE_FIX | Pending |
| T435 | Prevent web browsers from MIME sniffing | [skills/web-frontend-security/T435-prevent-web-browsers-from-mime-sniffing/SKILL.md](./skills/web-frontend-security/T435-prevent-web-browsers-from-mime-sniffing/SKILL.md) | 4 | CODE_FIX | Pending |
| T436 | Verify web browsers do not enable MIME sniffing | [skills/web-frontend-security/T436-verify-web-browsers-do-not-enable-mime-sniffing/SKILL.md](./skills/web-frontend-security/T436-verify-web-browsers-do-not-enable-mime-sniffing/SKILL.md) | 4 | CODE_FIX | Pending |
| T512 | Restrict access to opener in the opened window | [skills/web-frontend-security/T512-restrict-access-to-opener-in-the-opened-window/SKILL.md](./skills/web-frontend-security/T512-restrict-access-to-opener-in-the-opened-window/SKILL.md) | 4 | CODE_FIX | Pending |
| T513 | Verify that access to the opener is restricted in opened window | [skills/web-frontend-security/T513-verify-that-access-to-the-opener-is-restricted-in/SKILL.md](./skills/web-frontend-security/T513-verify-that-access-to-the-opener-is-restricted-in/SKILL.md) | 4 | CODE_FIX | Pending |
| T1469 | Prevent sensitive data leakage through Content Security Policy (CSP) reports | [skills/web-frontend-security/T1469-prevent-sensitive-data-leakage-through-content-sec/SKILL.md](./skills/web-frontend-security/T1469-prevent-sensitive-data-leakage-through-content-sec/SKILL.md) | 5 | CODE_FIX | Pending |
| T1541 | Decide on the best CSRF defense for your application | [skills/web-frontend-security/T1541-decide-on-the-best-csrf-defense-for-your-applicati/SKILL.md](./skills/web-frontend-security/T1541-decide-on-the-best-csrf-defense-for-your-applicati/SKILL.md) | 7 | CODE_FIX | Pending |
| T1543 | Leverage origin isolation for compartmentalization | [skills/web-frontend-security/T1543-leverage-origin-isolation-for-compartmentalization/SKILL.md](./skills/web-frontend-security/T1543-leverage-origin-isolation-for-compartmentalization/SKILL.md) | 5 | CODE_FIX | Pending |
| T1544 | Isolate untrusted content in a sandbox | [skills/web-frontend-security/T1544-isolate-untrusted-content-in-a-sandbox/SKILL.md](./skills/web-frontend-security/T1544-isolate-untrusted-content-in-a-sandbox/SKILL.md) | 5 | CODE_FIX | Pending |
| T1873 | Prevent information leakage through HTTP response headers | [skills/web-frontend-security/T1873-prevent-information-leakage-through-http-response/SKILL.md](./skills/web-frontend-security/T1873-prevent-information-leakage-through-http-response/SKILL.md) | 5 | CODE_FIX | Pending |
| T1874 | Test that HTTP response headers do not expose any sensitive information | [skills/web-frontend-security/T1874-test-that-http-response-headers-do-not-expose-any/SKILL.md](./skills/web-frontend-security/T1874-test-that-http-response-headers-do-not-expose-any/SKILL.md) | 5 | CODE_FIX | Pending |

### logging-audit (16)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T45 | Log potential critical security events | [skills/logging-audit/T45-log-potential-critical-security-events/SKILL.md](./skills/logging-audit/T45-log-potential-critical-security-events/SKILL.md) | 5 | CODE_FIX | Pending |
| T46 | Do not log confidential data | [skills/logging-audit/T46-do-not-log-confidential-data/SKILL.md](./skills/logging-audit/T46-do-not-log-confidential-data/SKILL.md) | 4 | CODE_FIX | Pending |
| T71 | Capture sufficient information for each transaction in audit logs | [skills/logging-audit/T71-capture-sufficient-information-for-each-transactio/SKILL.md](./skills/logging-audit/T71-capture-sufficient-information-for-each-transactio/SKILL.md) | 3 | CODE_FIX | Pending |
| T105 | Verify that your application does not have unnecessary debug capability or leftover test/debug code | [skills/logging-audit/T105-verify-that-your-application-does-not-have-unneces/SKILL.md](./skills/logging-audit/T105-verify-that-your-application-does-not-have-unneces/SKILL.md) | 7 | CODE_FIX | Pending |
| T159 | Follow best practices for secure error and exception handling | [skills/logging-audit/T159-follow-best-practices-for-secure-error-and-excepti/SKILL.md](./skills/logging-audit/T159-follow-best-practices-for-secure-error-and-excepti/SKILL.md) | 5 | CODE_FIX | Pending |
| T229 | Verify that logs do not contain confidential data | [skills/logging-audit/T229-verify-that-logs-do-not-contain-confidential-data/SKILL.md](./skills/logging-audit/T229-verify-that-logs-do-not-contain-confidential-data/SKILL.md) | 4 | CODE_FIX | Pending |
| T232 | Verify that end-user transaction logs capture sufficient information | [skills/logging-audit/T232-verify-that-end-user-transaction-logs-capture-suff/SKILL.md](./skills/logging-audit/T232-verify-that-end-user-transaction-logs-capture-suff/SKILL.md) | 3 | CODE_FIX | Pending |
| T315 | Verify that potential security-critical events are logged | [skills/logging-audit/T315-verify-that-potential-security-critical-events-are/SKILL.md](./skills/logging-audit/T315-verify-that-potential-security-critical-events-are/SKILL.md) | 5 | CODE_FIX | Pending |
| T350 | Verify that audit information is sufficiently protected | [skills/logging-audit/T350-verify-that-audit-information-is-sufficiently-prot/SKILL.md](./skills/logging-audit/T350-verify-that-audit-information-is-sufficiently-prot/SKILL.md) | 7 | CODE_FIX | Pending |
| T403 | Verify that errors and exceptions are securely handled | [skills/logging-audit/T403-verify-that-errors-and-exceptions-are-securely-han/SKILL.md](./skills/logging-audit/T403-verify-that-errors-and-exceptions-are-securely-han/SKILL.md) | 5 | CODE_FIX | Pending |
| T431 | Design a response to logging failures and other minor failures | [skills/logging-audit/T431-design-a-response-to-logging-failures-and-other-mi/SKILL.md](./skills/logging-audit/T431-design-a-response-to-logging-failures-and-other-mi/SKILL.md) | 4 | CODE_FIX | Pending |
| T432 | Test that logging failures and other minor failures are securely handled | [skills/logging-audit/T432-test-that-logging-failures-and-other-minor-failure/SKILL.md](./skills/logging-audit/T432-test-that-logging-failures-and-other-minor-failure/SKILL.md) | 4 | CODE_FIX | Pending |
| T437 | Include log reduction and report generation capabilities | [skills/logging-audit/T437-include-log-reduction-and-report-generation-capabi/SKILL.md](./skills/logging-audit/T437-include-log-reduction-and-report-generation-capabi/SKILL.md) | 4 | CODE_FIX | Pending |
| T438 | Verify that log reduction and report generation capabilities exist | [skills/logging-audit/T438-verify-that-log-reduction-and-report-generation-ca/SKILL.md](./skills/logging-audit/T438-verify-that-log-reduction-and-report-generation-ca/SKILL.md) | 4 | CODE_FIX | Pending |
| T485 | Sign audit records for non-repudiation | [skills/logging-audit/T485-sign-audit-records-for-non-repudiation/SKILL.md](./skills/logging-audit/T485-sign-audit-records-for-non-repudiation/SKILL.md) | 5 | CODE_FIX | Pending |
| T486 | Verify that audit records are signed to enable non-repudiation | [skills/logging-audit/T486-verify-that-audit-records-are-signed-to-enable-non/SKILL.md](./skills/logging-audit/T486-verify-that-audit-records-are-signed-to-enable-non/SKILL.md) | 5 | CODE_FIX | Pending |

### file-handling (14)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T53 | Prevent the upload of malicious files and implement anti-malware solutions | [skills/file-handling/T53-prevent-the-upload-of-malicious-files-and-implemen/SKILL.md](./skills/file-handling/T53-prevent-the-upload-of-malicious-files-and-implemen/SKILL.md) | 5 | CODE_FIX | Pending |
| T54 | Validate file contents | [skills/file-handling/T54-validate-file-contents/SKILL.md](./skills/file-handling/T54-validate-file-contents/SKILL.md) | 6 | CODE_FIX | Pending |
| T107 | Test that application forbids uploading or transferring malware | [skills/file-handling/T107-test-that-application-forbids-uploading-or-transfe/SKILL.md](./skills/file-handling/T107-test-that-application-forbids-uploading-or-transfe/SKILL.md) | 5 | CODE_FIX | Pending |
| T129 | Test for reliance on file name or extension of externally-supplied file | [skills/file-handling/T129-test-for-reliance-on-file-name-or-extension-of-ext/SKILL.md](./skills/file-handling/T129-test-for-reliance-on-file-name-or-extension-of-ext/SKILL.md) | 6 | CODE_FIX | Pending |
| T157 | Temporary files must be cleaned up after the resource is used | [skills/file-handling/T157-temporary-files-must-be-cleaned-up-after-the-resou/SKILL.md](./skills/file-handling/T157-temporary-files-must-be-cleaned-up-after-the-resou/SKILL.md) | 6 | CODE_FIX | Pending |
| T162 | Validate pathname before retrieving local resources | [skills/file-handling/T162-validate-pathname-before-retrieving-local-resource/SKILL.md](./skills/file-handling/T162-validate-pathname-before-retrieving-local-resource/SKILL.md) | 5 | CODE_FIX | Pending |
| T297 | Verify that target pathname is validated before retrieving local resources | [skills/file-handling/T297-verify-that-target-pathname-is-validated-before-re/SKILL.md](./skills/file-handling/T297-verify-that-target-pathname-is-validated-before-re/SKILL.md) | 5 | CODE_FIX | Pending |
| T300 | Test that temporary files are cleaned up after the resource is used | [skills/file-handling/T300-test-that-temporary-files-are-cleaned-up-after-the/SKILL.md](./skills/file-handling/T300-test-that-temporary-files-are-cleaned-up-after-the/SKILL.md) | 6 | CODE_FIX | Pending |
| T345 | Check the integrity of critical configuration and data files | [skills/file-handling/T345-check-the-integrity-of-critical-configuration-and/SKILL.md](./skills/file-handling/T345-check-the-integrity-of-critical-configuration-and/SKILL.md) | 4 | CODE_FIX | Pending |
| T346 | Test that the integrity of important configuration and data files are checked | [skills/file-handling/T346-test-that-the-integrity-of-important-configuration/SKILL.md](./skills/file-handling/T346-test-that-the-integrity-of-important-configuration/SKILL.md) | 4 | CODE_FIX | Pending |
| T375 | Release resources when no longer needed | [skills/file-handling/T375-release-resources-when-no-longer-needed/SKILL.md](./skills/file-handling/T375-release-resources-when-no-longer-needed/SKILL.md) | 6 | CODE_FIX | Pending |
| T572 | Check for symlinks before opening files | [skills/file-handling/T572-check-for-symlinks-before-opening-files/SKILL.md](./skills/file-handling/T572-check-for-symlinks-before-opening-files/SKILL.md) | 6 | CODE_FIX | Pending |
| T595 | Test that your application checks for symlinks before opening files | [skills/file-handling/T595-test-that-your-application-checks-for-symlinks-bef/SKILL.md](./skills/file-handling/T595-test-that-your-application-checks-for-symlinks-bef/SKILL.md) | 6 | CODE_FIX | Pending |
| T2167 | Secure file storage | [skills/file-handling/T2167-secure-file-storage/SKILL.md](./skills/file-handling/T2167-secure-file-storage/SKILL.md) | 6 | CODE_FIX | Pending |

### clinical-safety-resilience (11)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T205 | Avoid inter-process race conditions | [skills/clinical-safety-resilience/T205-avoid-inter-process-race-conditions/SKILL.md](./skills/clinical-safety-resilience/T205-avoid-inter-process-race-conditions/SKILL.md) | 5 | CODE_FIX | Pending |
| T342 | Inform and warn users about using critical system services | [skills/clinical-safety-resilience/T342-inform-and-warn-users-about-using-critical-system/SKILL.md](./skills/clinical-safety-resilience/T342-inform-and-warn-users-about-using-critical-system/SKILL.md) | 5 | CODE_FIX | Pending |
| T343 | Test that proper system use notification is displayed or sent for critical features | [skills/clinical-safety-resilience/T343-test-that-proper-system-use-notification-is-displa/SKILL.md](./skills/clinical-safety-resilience/T343-test-that-proper-system-use-notification-is-displa/SKILL.md) | 5 | CODE_FIX | Pending |
| T347 | Fail to a known state with predefined outputs | [skills/clinical-safety-resilience/T347-fail-to-a-known-state-with-predefined-outputs/SKILL.md](./skills/clinical-safety-resilience/T347-fail-to-a-known-state-with-predefined-outputs/SKILL.md) | 4 | CODE_FIX | Pending |
| T348 | Verify that the system fails to a known state | [skills/clinical-safety-resilience/T348-verify-that-the-system-fails-to-a-known-state/SKILL.md](./skills/clinical-safety-resilience/T348-verify-that-the-system-fails-to-a-known-state/SKILL.md) | 4 | CODE_FIX | Pending |
| T363 | Design a priority scheme for application services and operations | [skills/clinical-safety-resilience/T363-design-a-priority-scheme-for-application-services/SKILL.md](./skills/clinical-safety-resilience/T363-design-a-priority-scheme-for-application-services/SKILL.md) | 8 | CODE_FIX | Pending |
| T433 | Design a fallback mechanism or a degraded mode for the system | [skills/clinical-safety-resilience/T433-design-a-fallback-mechanism-or-a-degraded-mode-for/SKILL.md](./skills/clinical-safety-resilience/T433-design-a-fallback-mechanism-or-a-degraded-mode-for/SKILL.md) | 8 | CODE_FIX | Pending |
| T434 | Verify that the system has a fallback mechanism or a degraded mode | [skills/clinical-safety-resilience/T434-verify-that-the-system-has-a-fallback-mechanism-or/SKILL.md](./skills/clinical-safety-resilience/T434-verify-that-the-system-has-a-fallback-mechanism-or/SKILL.md) | 8 | CODE_FIX | Pending |
| T633 | Mitigate Deadlock and Recursion in Services | [skills/clinical-safety-resilience/T633-mitigate-deadlock-and-recursion-in-services/SKILL.md](./skills/clinical-safety-resilience/T633-mitigate-deadlock-and-recursion-in-services/SKILL.md) | 4 | CODE_FIX | Pending |
| T2280 | Verify that a priority scheme for application services and operations is designed | [skills/clinical-safety-resilience/T2280-verify-that-a-priority-scheme-for-application-serv/SKILL.md](./skills/clinical-safety-resilience/T2280-verify-that-a-priority-scheme-for-application-serv/SKILL.md) | 8 | CODE_FIX | Pending |
| T4602 | Utilize watchdog timers to ensure devices can quickly detect whether a system is unresponsive | [skills/clinical-safety-resilience/T4602-utilize-watchdog-timers-to-ensure-devices-can-quic/SKILL.md](./skills/clinical-safety-resilience/T4602-utilize-watchdog-timers-to-ensure-devices-can-quic/SKILL.md) | 7 | CODE_FIX | Pending |

### privacy (16)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T177 | Allow users to review and update their personal information | [skills/privacy/T177-allow-users-to-review-and-update-their-personal-in/SKILL.md](./skills/privacy/T177-allow-users-to-review-and-update-their-personal-in/SKILL.md) | 6 | CODE_FIX | Pending |
| T179 | Allow access for users to remove their personal information from the system | [skills/privacy/T179-allow-access-for-users-to-remove-their-personal-in/SKILL.md](./skills/privacy/T179-allow-access-for-users-to-remove-their-personal-in/SKILL.md) | 6 | CODE_FIX | Pending |
| T238 | Test that users can review and update their personal information | [skills/privacy/T238-test-that-users-can-review-and-update-their-person/SKILL.md](./skills/privacy/T238-test-that-users-can-review-and-update-their-person/SKILL.md) | 6 | CODE_FIX | Pending |
| T239 | Test that users provide consent prior to the collection of personal information | [skills/privacy/T239-test-that-users-provide-consent-prior-to-the-colle/SKILL.md](./skills/privacy/T239-test-that-users-provide-consent-prior-to-the-colle/SKILL.md) | 10 | CODE_FIX | Pending |
| T240 | Test whether users can remove their data from the system | [skills/privacy/T240-test-whether-users-can-remove-their-data-from-the/SKILL.md](./skills/privacy/T240-test-whether-users-can-remove-their-data-from-the/SKILL.md) | 6 | CODE_FIX | Pending |
| T313 | Identify and classify categories of personal information | [skills/privacy/T313-identify-and-classify-categories-of-personal-infor/SKILL.md](./skills/privacy/T313-identify-and-classify-categories-of-personal-infor/SKILL.md) | 5 | CODE_FIX | Pending |
| T314 | Verify that personal and confidential information is identified and classified | [skills/privacy/T314-verify-that-personal-and-confidential-information/SKILL.md](./skills/privacy/T314-verify-that-personal-and-confidential-information/SKILL.md) | 5 | CODE_FIX | Pending |
| T545 | Verify that personal information is anonymized before being reused for secondary purposes | [skills/privacy/T545-verify-that-personal-information-is-anonymized-bef/SKILL.md](./skills/privacy/T545-verify-that-personal-information-is-anonymized-bef/SKILL.md) | 8 | CODE_FIX | Pending |
| T607 | Develop automated tools/settings for destroying personal information when it is no longer needed | [skills/privacy/T607-develop-automated-tools-settings-for-destroying-pe/SKILL.md](./skills/privacy/T607-develop-automated-tools-settings-for-destroying-pe/SKILL.md) | 4 | CODE_FIX | Pending |
| T735 | Verify that personal information is removed when it is no longer needed | [skills/privacy/T735-verify-that-personal-information-is-removed-when-i/SKILL.md](./skills/privacy/T735-verify-that-personal-information-is-removed-when-i/SKILL.md) | 4 | CODE_FIX | Pending |
| T740 | Provide personal information and its processing information to users in an appropriate format | [skills/privacy/T740-provide-personal-information-and-its-processing-in/SKILL.md](./skills/privacy/T740-provide-personal-information-and-its-processing-in/SKILL.md) | 5 | CODE_FIX | Pending |
| T741 | Verify if users are provided with their personal data and its processing information in an appropriate format | [skills/privacy/T741-verify-if-users-are-provided-with-their-personal-d/SKILL.md](./skills/privacy/T741-verify-if-users-are-provided-with-their-personal-d/SKILL.md) | 5 | CODE_FIX | Pending |
| T743 | Verify accuracy of personal information | [skills/privacy/T743-verify-accuracy-of-personal-information/SKILL.md](./skills/privacy/T743-verify-accuracy-of-personal-information/SKILL.md) | 7 | CODE_FIX | Pending |
| T745 | Verify if pseudonymized personal information is protected | [skills/privacy/T745-verify-if-pseudonymized-personal-information-is-pr/SKILL.md](./skills/privacy/T745-verify-if-pseudonymized-personal-information-is-pr/SKILL.md) | 8 | CODE_FIX | Pending |
| T751 | Provide users with a notification of personal information processing | [skills/privacy/T751-provide-users-with-a-notification-of-personal-info/SKILL.md](./skills/privacy/T751-provide-users-with-a-notification-of-personal-info/SKILL.md) | 5 | CODE_FIX | Pending |
| T752 | Verify if users are notified about processing their personal information | [skills/privacy/T752-verify-if-users-are-notified-about-processing-thei/SKILL.md](./skills/privacy/T752-verify-if-users-are-notified-about-processing-thei/SKILL.md) | 5 | CODE_FIX | Pending |

### secure-config-supply-chain (19)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T62 | Protect passwords in property and configuration files | [skills/secure-config-supply-chain/T62-protect-passwords-in-property-and-configuration-fi/SKILL.md](./skills/secure-config-supply-chain/T62-protect-passwords-in-property-and-configuration-fi/SKILL.md) | 6 | CODE_FIX | Pending |
| T175 | Test that the client validates digital certificates | [skills/secure-config-supply-chain/T175-test-that-the-client-validates-digital-certificate/SKILL.md](./skills/secure-config-supply-chain/T175-test-that-the-client-validates-digital-certificate/SKILL.md) | 7 | CODE_FIX | Pending |
| T241 | Verify that third party libraries use secure settings and the latest patches | [skills/secure-config-supply-chain/T241-verify-that-third-party-libraries-use-secure-setti/SKILL.md](./skills/secure-config-supply-chain/T241-verify-that-third-party-libraries-use-secure-setti/SKILL.md) | 10 | CODE_FIX | Pending |
| T305 | Verify that your application dynamically loads code only from secure locations | [skills/secure-config-supply-chain/T305-verify-that-your-application-dynamically-loads-cod/SKILL.md](./skills/secure-config-supply-chain/T305-verify-that-your-application-dynamically-loads-cod/SKILL.md) | 8 | CODE_FIX | Pending |
| T370 | Follow best practices for using third-party software libraries/modules and open source/COTS components | [skills/secure-config-supply-chain/T370-follow-best-practices-for-using-third-party-softwa/SKILL.md](./skills/secure-config-supply-chain/T370-follow-best-practices-for-using-third-party-softwa/SKILL.md) | 6 | CODE_FIX | Pending |
| T371 | Provide unified and manageable interfaces for security settings and configuration parameters | [skills/secure-config-supply-chain/T371-provide-unified-and-manageable-interfaces-for-secu/SKILL.md](./skills/secure-config-supply-chain/T371-provide-unified-and-manageable-interfaces-for-secu/SKILL.md) | 4 | CODE_FIX | Pending |
| T379 | Provide sufficient documentation for security-related features | [skills/secure-config-supply-chain/T379-provide-sufficient-documentation-for-security-rela/SKILL.md](./skills/secure-config-supply-chain/T379-provide-sufficient-documentation-for-security-rela/SKILL.md) | 4 | CODE_FIX | Pending |
| T445 | Verify that only approved cryptographic algorithms and key lengths are used | [skills/secure-config-supply-chain/T445-verify-that-only-approved-cryptographic-algorithms/SKILL.md](./skills/secure-config-supply-chain/T445-verify-that-only-approved-cryptographic-algorithms/SKILL.md) | 8 | CODE_FIX | Pending |
| T446 | Verify that only standard libraries are used for cryptography | [skills/secure-config-supply-chain/T446-verify-that-only-standard-libraries-are-used-for-c/SKILL.md](./skills/secure-config-supply-chain/T446-verify-that-only-standard-libraries-are-used-for-c/SKILL.md) | 8 | CODE_FIX | Pending |
| T587 | Verify that cryptographically secure algorithms are used for random number generation | [skills/secure-config-supply-chain/T587-verify-that-cryptographically-secure-algorithms-ar/SKILL.md](./skills/secure-config-supply-chain/T587-verify-that-cryptographically-secure-algorithms-ar/SKILL.md) | 7 | CODE_FIX | Pending |
| T1364 | Verify that third party software libraries/modules and open source/COTS components are used securely | [skills/secure-config-supply-chain/T1364-verify-that-third-party-software-libraries-modules/SKILL.md](./skills/secure-config-supply-chain/T1364-verify-that-third-party-software-libraries-modules/SKILL.md) | 6 | CODE_FIX | Pending |
| T2273 | Verify that unified and manageable interfaces are available for security settings and configuration parameters | [skills/secure-config-supply-chain/T2273-verify-that-unified-and-manageable-interfaces-are/SKILL.md](./skills/secure-config-supply-chain/T2273-verify-that-unified-and-manageable-interfaces-are/SKILL.md) | 4 | CODE_FIX | Pending |
| T2288 | Design a secure application architecture for the cloud environment (Cloud) (1/2) | [skills/secure-config-supply-chain/T2288-design-a-secure-application-architecture-for-the-c/SKILL.md](./skills/secure-config-supply-chain/T2288-design-a-secure-application-architecture-for-the-c/SKILL.md) | 10 | CODE_FIX | Pending |
| T2300 | Verify that a secure application architecture is designed for the cloud environment (Cloud) | [skills/secure-config-supply-chain/T2300-verify-that-a-secure-application-architecture-is-d/SKILL.md](./skills/secure-config-supply-chain/T2300-verify-that-a-secure-application-architecture-is-d/SKILL.md) | 10 | CODE_FIX | Pending |
| T2349 | Configure software to have secure settings by default | [skills/secure-config-supply-chain/T2349-configure-software-to-have-secure-settings-by-defa/SKILL.md](./skills/secure-config-supply-chain/T2349-configure-software-to-have-secure-settings-by-defa/SKILL.md) | 8 | CODE_FIX | Pending |
| T2357 | Verify that software is configured to have secure settings by default | [skills/secure-config-supply-chain/T2357-verify-that-software-is-configured-to-have-secure/SKILL.md](./skills/secure-config-supply-chain/T2357-verify-that-software-is-configured-to-have-secure/SKILL.md) | 8 | CODE_FIX | Pending |
| T2361 | Design a secure application architecture for the cloud environment (Cloud) (2/2) | [skills/secure-config-supply-chain/T2361-design-a-secure-application-architecture-for-the-c/SKILL.md](./skills/secure-config-supply-chain/T2361-design-a-secure-application-architecture-for-the-c/SKILL.md) | 10 | CODE_FIX | Pending |
| T2477 | Test the re-deployment routines | [skills/secure-config-supply-chain/T2477-test-the-re-deployment-routines/SKILL.md](./skills/secure-config-supply-chain/T2477-test-the-re-deployment-routines/SKILL.md) | 6 | CODE_FIX | Pending |
| T2478 | Manage re-deployment routines | [skills/secure-config-supply-chain/T2478-manage-re-deployment-routines/SKILL.md](./skills/secure-config-supply-chain/T2478-manage-re-deployment-routines/SKILL.md) | 6 | CODE_FIX | Pending |

### database (6)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T2597 | Implement RBAC instead of individual accounts | [skills/database/T2597-implement-rbac-instead-of-individual-accounts/SKILL.md](./skills/database/T2597-implement-rbac-instead-of-individual-accounts/SKILL.md) | 10 | CODE_FIX | Pending |
| T2606 | Verify RBAC implemented instead of individual accounts | [skills/database/T2606-verify-rbac-implemented-instead-of-individual-acco/SKILL.md](./skills/database/T2606-verify-rbac-implemented-instead-of-individual-acco/SKILL.md) | 10 | CODE_FIX | Pending |
| T2607 | Verify query-level access control is implemented | [skills/database/T2607-verify-query-level-access-control-is-implemented/SKILL.md](./skills/database/T2607-verify-query-level-access-control-is-implemented/SKILL.md) | 8 | CODE_FIX | Pending |
| T2617 | Create dedicated database user accounts with minimum privileges (PostgreSQL) | [skills/database/T2617-create-dedicated-database-user-accounts-with-minim/SKILL.md](./skills/database/T2617-create-dedicated-database-user-accounts-with-minim/SKILL.md) | 8 | CODE_FIX | Pending |
| T2619 | Ensure that row-level security is correctly configured (PostgreSQL) | [skills/database/T2619-ensure-that-row-level-security-is-correctly-config/SKILL.md](./skills/database/T2619-ensure-that-row-level-security-is-correctly-config/SKILL.md) | 7 | CODE_FIX | Pending |
| T2664 | Create dedicated database user accounts with minimum privileges (Database Server) | [skills/database/T2664-create-dedicated-database-user-accounts-with-minim/SKILL.md](./skills/database/T2664-create-dedicated-database-user-accounts-with-minim/SKILL.md) | 8 | CODE_FIX | Pending |

### cloud-infrastructure (55)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T87 | Verify that all data in transit is encrypted using a secure TLS channel | [skills/cloud-infrastructure/T87-verify-that-all-data-in-transit-is-encrypted-using/SKILL.md](./skills/cloud-infrastructure/T87-verify-that-all-data-in-transit-is-encrypted-using/SKILL.md) | 8 | INFRA | Documented |
| T367 | Mitigate the security risks of power cut and power supply switch | [skills/cloud-infrastructure/T367-mitigate-the-security-risks-of-power-cut-and-power/SKILL.md](./skills/cloud-infrastructure/T367-mitigate-the-security-risks-of-power-cut-and-power/SKILL.md) | 5 | INFRA | Documented |
| T368 | Test system/application security in the event of a power cut or power supply switch | [skills/cloud-infrastructure/T368-test-system-application-security-in-the-event-of-a/SKILL.md](./skills/cloud-infrastructure/T368-test-system-application-security-in-the-event-of-a/SKILL.md) | 5 | INFRA | Documented |
| T456 | Change default security settings to the most stringent ones and disable unnecessary services and modules | [skills/cloud-infrastructure/T456-change-default-security-settings-to-the-most-strin/SKILL.md](./skills/cloud-infrastructure/T456-change-default-security-settings-to-the-most-strin/SKILL.md) | 6 | INFRA | Documented |
| T457 | Verify that unnecessary services and capabilities are disabled | [skills/cloud-infrastructure/T457-verify-that-unnecessary-services-and-capabilities/SKILL.md](./skills/cloud-infrastructure/T457-verify-that-unnecessary-services-and-capabilities/SKILL.md) | 6 | INFRA | Documented |
| T855 | Do not reveal sensitive personnel information through WHOIS Domain information | [skills/cloud-infrastructure/T855-do-not-reveal-sensitive-personnel-information-thro/SKILL.md](./skills/cloud-infrastructure/T855-do-not-reveal-sensitive-personnel-information-thro/SKILL.md) | 5 | INFRA | Documented |
| T856 | Keep your web server separate from other services | [skills/cloud-infrastructure/T856-keep-your-web-server-separate-from-other-services/SKILL.md](./skills/cloud-infrastructure/T856-keep-your-web-server-separate-from-other-services/SKILL.md) | 5 | INFRA | Documented |
| T857 | Test that no other service is installed on your web server | [skills/cloud-infrastructure/T857-test-that-no-other-service-is-installed-on-your-we/SKILL.md](./skills/cloud-infrastructure/T857-test-that-no-other-service-is-installed-on-your-we/SKILL.md) | 5 | INFRA | Documented |
| T858 | Use the vendor supplied version of binaries | [skills/cloud-infrastructure/T858-use-the-vendor-supplied-version-of-binaries/SKILL.md](./skills/cloud-infrastructure/T858-use-the-vendor-supplied-version-of-binaries/SKILL.md) | 4 | INFRA | Documented |
| T1881 | Mitigate the risk of uncontrolled data harvesting | [skills/cloud-infrastructure/T1881-mitigate-the-risk-of-uncontrolled-data-harvesting/SKILL.md](./skills/cloud-infrastructure/T1881-mitigate-the-risk-of-uncontrolled-data-harvesting/SKILL.md) | 4 | INFRA | Documented |
| T1882 | Verify uncontrolled data harvesting can be detected | [skills/cloud-infrastructure/T1882-verify-uncontrolled-data-harvesting-can-be-detecte/SKILL.md](./skills/cloud-infrastructure/T1882-verify-uncontrolled-data-harvesting-can-be-detecte/SKILL.md) | 4 | INFRA | Documented |
| T2158 | Ensure that data is deleted securely and efficiently from storage (Cloud) | [skills/cloud-infrastructure/T2158-ensure-that-data-is-deleted-securely-and-efficient/SKILL.md](./skills/cloud-infrastructure/T2158-ensure-that-data-is-deleted-securely-and-efficient/SKILL.md) | 7 | INFRA | Documented |
| T2159 | Ensure security of virtualized environments (Cloud) | [skills/cloud-infrastructure/T2159-ensure-security-of-virtualized-environments-cloud/SKILL.md](./skills/cloud-infrastructure/T2159-ensure-security-of-virtualized-environments-cloud/SKILL.md) | 10 | INFRA | Documented |
| T2161 | Ensure the cloud management interface is secured properly (Cloud) | [skills/cloud-infrastructure/T2161-ensure-the-cloud-management-interface-is-secured-p/SKILL.md](./skills/cloud-infrastructure/T2161-ensure-the-cloud-management-interface-is-secured-p/SKILL.md) | 9 | INFRA | Documented |
| T2163 | Ensure the security of hypervisors (Cloud) | [skills/cloud-infrastructure/T2163-ensure-the-security-of-hypervisors-cloud/SKILL.md](./skills/cloud-infrastructure/T2163-ensure-the-security-of-hypervisors-cloud/SKILL.md) | 9 | INFRA | Documented |
| T2285 | Set up and maintain cloud users and roles (Cloud) | [skills/cloud-infrastructure/T2285-set-up-and-maintain-cloud-users-and-roles-cloud/SKILL.md](./skills/cloud-infrastructure/T2285-set-up-and-maintain-cloud-users-and-roles-cloud/SKILL.md) | 10 | INFRA | Documented |
| T2286 | Configure a secure user authentication (Cloud) (1/2) | [skills/cloud-infrastructure/T2286-configure-a-secure-user-authentication-cloud-1-2/SKILL.md](./skills/cloud-infrastructure/T2286-configure-a-secure-user-authentication-cloud-1-2/SKILL.md) | 10 | INFRA | Documented |
| T2287 | Configure a secure user authorization (Cloud) (1/2) | [skills/cloud-infrastructure/T2287-configure-a-secure-user-authorization-cloud-1-2/SKILL.md](./skills/cloud-infrastructure/T2287-configure-a-secure-user-authorization-cloud-1-2/SKILL.md) | 10 | INFRA | Documented |
| T2289 | Secure network access control (Cloud) (1/4) | [skills/cloud-infrastructure/T2289-secure-network-access-control-cloud-1-4/SKILL.md](./skills/cloud-infrastructure/T2289-secure-network-access-control-cloud-1-4/SKILL.md) | 10 | INFRA | Documented |
| T2290 | Secure data in transit (Cloud) (1/2) | [skills/cloud-infrastructure/T2290-secure-data-in-transit-cloud-1-2/SKILL.md](./skills/cloud-infrastructure/T2290-secure-data-in-transit-cloud-1-2/SKILL.md) | 10 | INFRA | Documented |
| T2291 | Secure hosts and operating systems (Cloud) | [skills/cloud-infrastructure/T2291-secure-hosts-and-operating-systems-cloud/SKILL.md](./skills/cloud-infrastructure/T2291-secure-hosts-and-operating-systems-cloud/SKILL.md) | 10 | INFRA | Documented |
| T2292 | Protect data at rest (Cloud) (1/3) | [skills/cloud-infrastructure/T2292-protect-data-at-rest-cloud-1-3/SKILL.md](./skills/cloud-infrastructure/T2292-protect-data-at-rest-cloud-1-3/SKILL.md) | 10 | INFRA | Documented |
| T2293 | Enable logging and protect log files in your cloud environment (Cloud) (1/4) | [skills/cloud-infrastructure/T2293-enable-logging-and-protect-log-files-in-your-cloud/SKILL.md](./skills/cloud-infrastructure/T2293-enable-logging-and-protect-log-files-in-your-cloud/SKILL.md) | 9 | INFRA | Documented |
| T2294 | Enable logs and configuration monitoring in your cloud environment (Cloud) (1/4) | [skills/cloud-infrastructure/T2294-enable-logs-and-configuration-monitoring-in-your-c/SKILL.md](./skills/cloud-infrastructure/T2294-enable-logs-and-configuration-monitoring-in-your-c/SKILL.md) | 8 | INFRA | Documented |
| T2295 | Secure cloud key management system (Cloud) | [skills/cloud-infrastructure/T2295-secure-cloud-key-management-system-cloud/SKILL.md](./skills/cloud-infrastructure/T2295-secure-cloud-key-management-system-cloud/SKILL.md) | 10 | INFRA | Documented |
| T2297 | Verify that cloud users and roles are set up and maintained (Cloud) | [skills/cloud-infrastructure/T2297-verify-that-cloud-users-and-roles-are-set-up-and-m/SKILL.md](./skills/cloud-infrastructure/T2297-verify-that-cloud-users-and-roles-are-set-up-and-m/SKILL.md) | 10 | INFRA | Documented |
| T2298 | Verify that user authentication is securely configured (Cloud) | [skills/cloud-infrastructure/T2298-verify-that-user-authentication-is-securely-config/SKILL.md](./skills/cloud-infrastructure/T2298-verify-that-user-authentication-is-securely-config/SKILL.md) | 10 | INFRA | Documented |
| T2299 | Verify that user authorization is securely configured (Cloud) | [skills/cloud-infrastructure/T2299-verify-that-user-authorization-is-securely-configu/SKILL.md](./skills/cloud-infrastructure/T2299-verify-that-user-authorization-is-securely-configu/SKILL.md) | 10 | INFRA | Documented |
| T2301 | Verify that network access control is secured (Cloud) | [skills/cloud-infrastructure/T2301-verify-that-network-access-control-is-secured-clou/SKILL.md](./skills/cloud-infrastructure/T2301-verify-that-network-access-control-is-secured-clou/SKILL.md) | 10 | INFRA | Documented |
| T2302 | Verify that data in transit is secured (Cloud) | [skills/cloud-infrastructure/T2302-verify-that-data-in-transit-is-secured-cloud/SKILL.md](./skills/cloud-infrastructure/T2302-verify-that-data-in-transit-is-secured-cloud/SKILL.md) | 10 | INFRA | Documented |
| T2303 | Verify that hosts and operating systems are secure (Cloud) | [skills/cloud-infrastructure/T2303-verify-that-hosts-and-operating-systems-are-secure/SKILL.md](./skills/cloud-infrastructure/T2303-verify-that-hosts-and-operating-systems-are-secure/SKILL.md) | 10 | INFRA | Documented |
| T2304 | Verify that data at rest is protected (Cloud) | [skills/cloud-infrastructure/T2304-verify-that-data-at-rest-is-protected-cloud/SKILL.md](./skills/cloud-infrastructure/T2304-verify-that-data-at-rest-is-protected-cloud/SKILL.md) | 10 | INFRA | Documented |
| T2305 | Verify that logging is enabled and log files are protected (Cloud) (1/2) | [skills/cloud-infrastructure/T2305-verify-that-logging-is-enabled-and-log-files-are-p/SKILL.md](./skills/cloud-infrastructure/T2305-verify-that-logging-is-enabled-and-log-files-are-p/SKILL.md) | 9 | INFRA | Documented |
| T2306 | Verify that log monitoring and configuration monitoring are enabled (Cloud) (1/3) | [skills/cloud-infrastructure/T2306-verify-that-log-monitoring-and-configuration-monit/SKILL.md](./skills/cloud-infrastructure/T2306-verify-that-log-monitoring-and-configuration-monit/SKILL.md) | 8 | INFRA | Documented |
| T2307 | Verify that the key management system is secured (Cloud) | [skills/cloud-infrastructure/T2307-verify-that-the-key-management-system-is-secured-c/SKILL.md](./skills/cloud-infrastructure/T2307-verify-that-the-key-management-system-is-secured-c/SKILL.md) | 10 | INFRA | Documented |
| T2359 | Configure a secure user authentication (Cloud) (2/2) | [skills/cloud-infrastructure/T2359-configure-a-secure-user-authentication-cloud-2-2/SKILL.md](./skills/cloud-infrastructure/T2359-configure-a-secure-user-authentication-cloud-2-2/SKILL.md) | 10 | INFRA | Documented |
| T2360 | Configure a secure user authorization (Cloud) (2/2) | [skills/cloud-infrastructure/T2360-configure-a-secure-user-authorization-cloud-2-2/SKILL.md](./skills/cloud-infrastructure/T2360-configure-a-secure-user-authorization-cloud-2-2/SKILL.md) | 10 | INFRA | Documented |
| T2362 | Secure network access control (Cloud) (2/4) | [skills/cloud-infrastructure/T2362-secure-network-access-control-cloud-2-4/SKILL.md](./skills/cloud-infrastructure/T2362-secure-network-access-control-cloud-2-4/SKILL.md) | 10 | INFRA | Documented |
| T2363 | Secure network access control (Cloud) (3/4) | [skills/cloud-infrastructure/T2363-secure-network-access-control-cloud-3-4/SKILL.md](./skills/cloud-infrastructure/T2363-secure-network-access-control-cloud-3-4/SKILL.md) | 10 | INFRA | Documented |
| T2364 | Secure network access control (Cloud) (4/4) | [skills/cloud-infrastructure/T2364-secure-network-access-control-cloud-4-4/SKILL.md](./skills/cloud-infrastructure/T2364-secure-network-access-control-cloud-4-4/SKILL.md) | 10 | INFRA | Documented |
| T2365 | Secure data in transit (Cloud) (2/2) | [skills/cloud-infrastructure/T2365-secure-data-in-transit-cloud-2-2/SKILL.md](./skills/cloud-infrastructure/T2365-secure-data-in-transit-cloud-2-2/SKILL.md) | 10 | INFRA | Documented |
| T2366 | Protect data at rest (Cloud) (2/3) | [skills/cloud-infrastructure/T2366-protect-data-at-rest-cloud-2-3/SKILL.md](./skills/cloud-infrastructure/T2366-protect-data-at-rest-cloud-2-3/SKILL.md) | 10 | INFRA | Documented |
| T2367 | Protect data at rest (Cloud) (3/3) | [skills/cloud-infrastructure/T2367-protect-data-at-rest-cloud-3-3/SKILL.md](./skills/cloud-infrastructure/T2367-protect-data-at-rest-cloud-3-3/SKILL.md) | 10 | INFRA | Documented |
| T2368 | Enable logging and protect log files in your cloud environment (Cloud) (2/4) | [skills/cloud-infrastructure/T2368-enable-logging-and-protect-log-files-in-your-cloud/SKILL.md](./skills/cloud-infrastructure/T2368-enable-logging-and-protect-log-files-in-your-cloud/SKILL.md) | 9 | INFRA | Documented |
| T2369 | Enable logging and protect log files in your cloud environment (Cloud) (3/4) | [skills/cloud-infrastructure/T2369-enable-logging-and-protect-log-files-in-your-cloud/SKILL.md](./skills/cloud-infrastructure/T2369-enable-logging-and-protect-log-files-in-your-cloud/SKILL.md) | 9 | INFRA | Documented |
| T2370 | Enable logging and protect log files in your cloud environment (Cloud) (4/4) | [skills/cloud-infrastructure/T2370-enable-logging-and-protect-log-files-in-your-cloud/SKILL.md](./skills/cloud-infrastructure/T2370-enable-logging-and-protect-log-files-in-your-cloud/SKILL.md) | 9 | INFRA | Documented |
| T2371 | Enable logs and configuration monitoring in your cloud environment (Cloud) (2/4) | [skills/cloud-infrastructure/T2371-enable-logs-and-configuration-monitoring-in-your-c/SKILL.md](./skills/cloud-infrastructure/T2371-enable-logs-and-configuration-monitoring-in-your-c/SKILL.md) | 8 | INFRA | Documented |
| T2372 | Enable logs and configuration monitoring in your cloud environment (Cloud) (3/4) | [skills/cloud-infrastructure/T2372-enable-logs-and-configuration-monitoring-in-your-c/SKILL.md](./skills/cloud-infrastructure/T2372-enable-logs-and-configuration-monitoring-in-your-c/SKILL.md) | 8 | INFRA | Documented |
| T2373 | Enable logs and configuration monitoring in your cloud environment (Cloud) (4/4) | [skills/cloud-infrastructure/T2373-enable-logs-and-configuration-monitoring-in-your-c/SKILL.md](./skills/cloud-infrastructure/T2373-enable-logs-and-configuration-monitoring-in-your-c/SKILL.md) | 8 | INFRA | Documented |
| T2374 | Verify that logging is enabled and log files are protected (Cloud) (2/2) | [skills/cloud-infrastructure/T2374-verify-that-logging-is-enabled-and-log-files-are-p/SKILL.md](./skills/cloud-infrastructure/T2374-verify-that-logging-is-enabled-and-log-files-are-p/SKILL.md) | 9 | INFRA | Documented |
| T2375 | Verify that log monitoring and configuration monitoring are enabled (Cloud) (2/3) | [skills/cloud-infrastructure/T2375-verify-that-log-monitoring-and-configuration-monit/SKILL.md](./skills/cloud-infrastructure/T2375-verify-that-log-monitoring-and-configuration-monit/SKILL.md) | 8 | INFRA | Documented |
| T2376 | Verify that log monitoring and configuration monitoring are enabled (Cloud) (3/3) | [skills/cloud-infrastructure/T2376-verify-that-log-monitoring-and-configuration-monit/SKILL.md](./skills/cloud-infrastructure/T2376-verify-that-log-monitoring-and-configuration-monit/SKILL.md) | 8 | INFRA | Documented |
| T4597 | Break and inspect SSL/TLS sessions | [skills/cloud-infrastructure/T4597-break-and-inspect-ssl-tls-sessions/SKILL.md](./skills/cloud-infrastructure/T4597-break-and-inspect-ssl-tls-sessions/SKILL.md) | 6 | INFRA | Documented |
| T4600 | Establish Out-of-Band Communications Channel | [skills/cloud-infrastructure/T4600-establish-out-of-band-communications-channel/SKILL.md](./skills/cloud-infrastructure/T4600-establish-out-of-band-communications-channel/SKILL.md) | 10 | INFRA | Documented |
| T4601 | Prioritize static network configuration | [skills/cloud-infrastructure/T4601-prioritize-static-network-configuration/SKILL.md](./skills/cloud-infrastructure/T4601-prioritize-static-network-configuration/SKILL.md) | 8 | INFRA | Documented |

### database-infrastructure (27)

| ID | Title | Skill File | Priority | Category | Status |
|----|-------|-----------|----------|----------|--------|
| T364 | Enable secure backup and restore capabilities | [skills/database-infrastructure/T364-enable-secure-backup-and-restore-capabilities/SKILL.md](./skills/database-infrastructure/T364-enable-secure-backup-and-restore-capabilities/SKILL.md) | 6 | INFRA | Documented |
| T365 | Verify the security of backing up and restoring procedures | [skills/database-infrastructure/T365-verify-the-security-of-backing-up-and-restoring-pr/SKILL.md](./skills/database-infrastructure/T365-verify-the-security-of-backing-up-and-restoring-pr/SKILL.md) | 6 | INFRA | Documented |
| T2601 | Use Transparent Data Encryption with Enterprise Databases | [skills/database-infrastructure/T2601-use-transparent-data-encryption-with-enterprise-da/SKILL.md](./skills/database-infrastructure/T2601-use-transparent-data-encryption-with-enterprise-da/SKILL.md) | 8 | INFRA | Documented |
| T2603 | Protect backup archive bits | [skills/database-infrastructure/T2603-protect-backup-archive-bits/SKILL.md](./skills/database-infrastructure/T2603-protect-backup-archive-bits/SKILL.md) | 7 | INFRA | Documented |
| T2604 | Follow best practices for data restoring operations | [skills/database-infrastructure/T2604-follow-best-practices-for-data-restoring-operation/SKILL.md](./skills/database-infrastructure/T2604-follow-best-practices-for-data-restoring-operation/SKILL.md) | 7 | INFRA | Documented |
| T2605 | Validate database traffic | [skills/database-infrastructure/T2605-validate-database-traffic/SKILL.md](./skills/database-infrastructure/T2605-validate-database-traffic/SKILL.md) | 9 | INFRA | Documented |
| T2610 | Verify that Transparent Data Encryption is utilized with Enterprise Databases | [skills/database-infrastructure/T2610-verify-that-transparent-data-encryption-is-utilize/SKILL.md](./skills/database-infrastructure/T2610-verify-that-transparent-data-encryption-is-utilize/SKILL.md) | 8 | INFRA | Documented |
| T2611 | Verify that typical database and server activities, along with related metadata, are logged | [skills/database-infrastructure/T2611-verify-that-typical-database-and-server-activities/SKILL.md](./skills/database-infrastructure/T2611-verify-that-typical-database-and-server-activities/SKILL.md) | 8 | INFRA | Documented |
| T2612 | Verify backup archive bits are protected | [skills/database-infrastructure/T2612-verify-backup-archive-bits-are-protected/SKILL.md](./skills/database-infrastructure/T2612-verify-backup-archive-bits-are-protected/SKILL.md) | 7 | INFRA | Documented |
| T2613 | Verify best practices for data-restoring operations are followed | [skills/database-infrastructure/T2613-verify-best-practices-for-data-restoring-operation/SKILL.md](./skills/database-infrastructure/T2613-verify-best-practices-for-data-restoring-operation/SKILL.md) | 7 | INFRA | Documented |
| T2614 | Verify database traffic is validated | [skills/database-infrastructure/T2614-verify-database-traffic-is-validated/SKILL.md](./skills/database-infrastructure/T2614-verify-database-traffic-is-validated/SKILL.md) | 9 | INFRA | Documented |
| T2615 | Limit network access by blocking connections from unknown IP addresses (PostgreSQL) | [skills/database-infrastructure/T2615-limit-network-access-by-blocking-connections-from/SKILL.md](./skills/database-infrastructure/T2615-limit-network-access-by-blocking-connections-from/SKILL.md) | 8 | INFRA | Documented |
| T2616 | Use a secure authentication mechanism for database connections (PostgreSQL) | [skills/database-infrastructure/T2616-use-a-secure-authentication-mechanism-for-database/SKILL.md](./skills/database-infrastructure/T2616-use-a-secure-authentication-mechanism-for-database/SKILL.md) | 9 | INFRA | Documented |
| T2618 | Remove unnecessary superuser accounts (PostgreSQL) | [skills/database-infrastructure/T2618-remove-unnecessary-superuser-accounts-postgresql/SKILL.md](./skills/database-infrastructure/T2618-remove-unnecessary-superuser-accounts-postgresql/SKILL.md) | 6 | INFRA | Documented |
| T2620 | Protect data in transit with TLS (PostgreSQL) | [skills/database-infrastructure/T2620-protect-data-in-transit-with-tls-postgresql/SKILL.md](./skills/database-infrastructure/T2620-protect-data-in-transit-with-tls-postgresql/SKILL.md) | 9 | INFRA | Documented |
| T2621 | Use file volume encryption and consider in-database encryption with pgcrypto (PostgreSQL) | [skills/database-infrastructure/T2621-use-file-volume-encryption-and-consider-in-databas/SKILL.md](./skills/database-infrastructure/T2621-use-file-volume-encryption-and-consider-in-databas/SKILL.md) | 8 | INFRA | Documented |
| T2622 | Monitor database activity and enable audit logging (PostgreSQL) | [skills/database-infrastructure/T2622-monitor-database-activity-and-enable-audit-logging/SKILL.md](./skills/database-infrastructure/T2622-monitor-database-activity-and-enable-audit-logging/SKILL.md) | 5 | INFRA | Documented |
| T2623 | Schedule regular database backups to protect availability (PostgreSQL) | [skills/database-infrastructure/T2623-schedule-regular-database-backups-to-protect-avail/SKILL.md](./skills/database-infrastructure/T2623-schedule-regular-database-backups-to-protect-avail/SKILL.md) | 6 | INFRA | Documented |
| T2652 | Consider adding plugins for stronger authentication protocols and stricter password complexity rules (MariaDB) | [skills/database-infrastructure/T2652-consider-adding-plugins-for-stronger-authenticatio/SKILL.md](./skills/database-infrastructure/T2652-consider-adding-plugins-for-stronger-authenticatio/SKILL.md) | 9 | INFRA | Documented |
| T2661 | Change insecure configuration defaults and remove unnecessary features | [skills/database-infrastructure/T2661-change-insecure-configuration-defaults-and-remove/SKILL.md](./skills/database-infrastructure/T2661-change-insecure-configuration-defaults-and-remove/SKILL.md) | 9 | INFRA | Documented |
| T2662 | Restrict network access to the database server | [skills/database-infrastructure/T2662-restrict-network-access-to-the-database-server/SKILL.md](./skills/database-infrastructure/T2662-restrict-network-access-to-the-database-server/SKILL.md) | 10 | INFRA | Documented |
| T2663 | Use a secure authentication mechanism for database connections | [skills/database-infrastructure/T2663-use-a-secure-authentication-mechanism-for-database/SKILL.md](./skills/database-infrastructure/T2663-use-a-secure-authentication-mechanism-for-database/SKILL.md) | 9 | INFRA | Documented |
| T2665 | Protect sensitive data at rest with encryption | [skills/database-infrastructure/T2665-protect-sensitive-data-at-rest-with-encryption/SKILL.md](./skills/database-infrastructure/T2665-protect-sensitive-data-at-rest-with-encryption/SKILL.md) | 8 | INFRA | Documented |
| T2666 | Protect data in transit with TLS (Database Server) | [skills/database-infrastructure/T2666-protect-data-in-transit-with-tls-database-server/SKILL.md](./skills/database-infrastructure/T2666-protect-data-in-transit-with-tls-database-server/SKILL.md) | 8 | INFRA | Documented |
| T2667 | Schedule regular database backups to protect availability (Database Server) | [skills/database-infrastructure/T2667-schedule-regular-database-backups-to-protect-avail/SKILL.md](./skills/database-infrastructure/T2667-schedule-regular-database-backups-to-protect-avail/SKILL.md) | 6 | INFRA | Documented |
| T2668 | Monitor database activity and enable audit logging | [skills/database-infrastructure/T2668-monitor-database-activity-and-enable-audit-logging/SKILL.md](./skills/database-infrastructure/T2668-monitor-database-activity-and-enable-audit-logging/SKILL.md) | 5 | INFRA | Documented |
| T3990 | Schedule regular backups | [skills/database-infrastructure/T3990-schedule-regular-backups/SKILL.md](./skills/database-infrastructure/T3990-schedule-regular-backups/SKILL.md) | 6 | INFRA | Documented |
## Completion Requirements

**ALL 316 file-tracked countermeasures must be addressed. No exceptions.** CODE_FIX items are complete only when the secure pattern is implemented and its success criteria are met. INFRA items are complete when the recommended Vercel/Supabase/IT action is carried out and recorded, plus any repo-side config the recipe names.

## Progress Tracking

| Domain | Total | Implemented | Documented | Remaining |
|--------|-------|-------------|------------|-----------|
| authentication | 38 | 0 | 0 | 38 |
| session-management | 23 | 0 | 0 | 23 |
| authorization | 22 | 0 | 0 | 22 |
| api-security | 8 | 0 | 0 | 8 |
| input-validation | 30 | 0 | 0 | 30 |
| web-frontend-security | 31 | 0 | 0 | 31 |
| logging-audit | 16 | 0 | 0 | 16 |
| file-handling | 14 | 0 | 0 | 14 |
| clinical-safety-resilience | 11 | 0 | 0 | 11 |
| privacy | 16 | 0 | 0 | 16 |
| secure-config-supply-chain | 19 | 0 | 0 | 19 |
| database | 6 | 0 | 0 | 6 |
| cloud-infrastructure | 55 | 0 | 55 | 0 |
| database-infrastructure | 27 | 0 | 27 | 0 |
| **TOTAL** | **316** | **0** | **82** | **234** |

**Remaining MUST reach 0 before completion.** INFRA rows are pre-documented (external actions), but each should still be re-evaluated for repo-side config during implementation.

## Verification Checklist

- [ ] All CODE_FIX countermeasures have secure implementations
- [ ] All non-code items documented with justification
- [ ] Total addressed = 316
<!-- SDE-SECURITY-HARDENING-END -->
