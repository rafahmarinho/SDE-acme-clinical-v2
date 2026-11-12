---
name: t2157-secure-email-and-messaging-in-web-applications
description: Secure the e-mail channel used by ACME Clinical's Supabase Auth flows (invite, recovery, e-mail change) - trusted SMTP provider over TLS, SPF/DKIM/DMARC on the sending domain, rate limits, no sensitive data in messages, and header-injection-safe addresses.
---

# T2157: Secure email and messaging in web applications

**Category:** CODE_FIX
**SD Elements:** [T2157](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T2157/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: services and database access. Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Password recovery and staff invitations are left on Supabase's built-in test mailer or a personal SMTP account, sent from a domain without SPF/DKIM/DMARC, so messages are spoofable or land in spam. Addresses typed by users may be passed unchecked to the mailer, and bulk sends to staff expose every recipient in CC.

**Secure Implementation Pattern:**
```toml
# supabase/config.toml - production mailer and limits (credentials from env, never inline)
[auth.email.smtp]
enabled = true
host = "smtp.provider.example"
port = 587                      # STARTTLS required by the provider
user = "env(SMTP_USER)"
pass = "env(SMTP_PASS)"
admin_email = "no-reply@acme-clinical.example"
sender_name = "ACME Clinical"

[auth.rate_limit]
email_sent = 10                 # per hour
```
```python
# backend/app/routers/staff.py - invite addresses are validated and canonicalised before reaching Supabase
class InviteIn(BaseModel):
    email: EmailStr                                  # email-validator; rejects CR/LF and display names
    @field_validator("email")
    @classmethod
    def _canon(cls, v: str) -> str:
        return canonical_email(v)                    # app.services.identity
```

**Implementation Guidance:**
- Use a trusted transactional e-mail provider that supports TLS, SPF, DKIM and DMARC; configure it in the Supabase project (SMTP settings) and mirror non-secret values in `supabase/config.toml` with `env(...)` placeholders. Publishing SPF/DKIM/DMARC DNS records for the sending domain is an INFRA step recorded in `docs/security/deployment.md`.
- All e-mails are sent by Supabase Auth from server-side flows; the backend never builds raw MIME or SMTP headers. Validate every address with `EmailStr` + `canonical_email` (`backend/app/routers/staff.py`, `frontend/src/screens/ForgotPassword.tsx`) so CR/LF header injection is impossible.
- Keep message content minimal: links only, no PHI, passwords or tokens beyond the single-use link (see T1386, T2); one recipient per message (no CC lists).
- Keep `[auth.rate_limit] email_sent` and `max_frequency` limits so the mailer cannot be abused for spam or enumeration.
- Staff accounts with admin rights use two-factor authentication (already enforced for admin sessions, see T1).
- Reference: SD Elements guidance for T2157.

**Success Criteria:**
- [ ] `backend/tests/test_authentication.py::test_supabase_auth_configuration_hardened` extended: `[auth.email.smtp]` uses `env(...)` for credentials and a TLS port; `email_sent` limit present.
- [ ] Pytest: invite with `"a@b.com\r\nBcc: x@evil.test"` returns 422.
- [ ] Manual check (recorded in `docs/security/deployment.md`): a test e-mail passes SPF, DKIM and DMARC alignment.

**Status:** Applied
