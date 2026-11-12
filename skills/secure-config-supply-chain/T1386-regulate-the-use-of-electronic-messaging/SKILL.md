---
name: t1386-regulate-the-use-of-electronic-messaging
description: Regulate the e-mails ACME Clinical sends (Supabase Auth invitations, password recovery, e-mail change and admin alerts) so that no patient data or credentials travel in message bodies, templates carry a standard notice and anti-phishing statement, and delivery uses TLS.
---

# T1386: Regulate the use of electronic messaging

**Category:** CODE_FIX
**SD Elements:** [T1386](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1386/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: Use current, stable versions of the technologies and Supabase for PostgreSQL, e-mail and password login, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
E-mail login and password recovery mean the system sends e-mail. A naive build reuses the default Supabase templates, or adds "alarm digest" or report e-mails containing patient names and vital signs, sends temporary passwords in invitation e-mails, and never tells staff that ACME will not ask for credentials by e-mail.

**Secure Implementation Pattern:**
```python
# backend/app/core/audit.py - admin notifications carry no PHI, only a pointer into the app
async def notify_admins(kind: str, details: dict | None = None) -> None:
    safe = {k: v for k, v in (details or {}).items() if k in NOTIFY_ALLOWED_KEYS}   # ids/counts only
    await insert_system_alert(kind=kind, details=safe)   # in-app alert; any e-mail says "sign in to view"
```
```html
<!-- supabase/templates/recovery.html (referenced from supabase/config.toml [auth.email.template.recovery]) -->
<p>A password reset was requested for your ACME Clinical account.</p>
<p><a href="{{ .ConfirmationURL }}">Reset your password</a> (link valid for 15 minutes).</p>
<p>ACME Clinical will never ask for your password or one-time codes by e-mail or phone.
   If you did not request this, report it to the service desk.</p>
<p class="disclaimer">Confidential: intended only for the named recipient.</p>
```

**Implementation Guidance:**
- Classification rule (document in `docs/security/data-classification.md`): data classed PHI or confidential is never placed in e-mail bodies, subjects or attachments; e-mails only link back to the authenticated app.
- Add custom Supabase Auth templates under `supabase/templates/` (invite, recovery, email change, password changed) and wire them in `supabase/config.toml`; include the standard disclaimer and the "we never ask for your password" statement; no passwords in any template (invites use a set-password link - see `test_invite_never_sends_a_password_and_uses_server_key`).
- Keep admin alerts (`notify_admins` in `backend/app/core/audit.py`, `public.system_alerts`) in-app; if e-mail forwarding is added later, send only the alert kind and a link.
- Configure a custom SMTP provider in Supabase with mandatory TLS (`[auth.email.smtp]`), and SPF/DKIM/DMARC for the sending domain (INFRA, see T2157).
- Staff training, DLP and service-desk procedures are organizational (PROCESS) and recorded outside the repo.
- Reference: SD Elements guidance for T1386.

**Success Criteria:**
- [ ] Pytest: every template in `supabase/templates/` contains the anti-phishing statement and disclaimer and no `{{ .Password }}`-like or patient-data placeholders.
- [ ] Pytest: `notify_admins` drops any detail key outside the allow-list (patient names, MRNs, vitals).
- [ ] `supabase/config.toml` references the custom templates and an SMTP block without inline credentials.

**Status:** Applied
