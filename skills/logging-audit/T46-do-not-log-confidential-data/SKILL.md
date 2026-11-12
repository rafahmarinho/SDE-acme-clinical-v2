---
name: t46-do-not-log-confidential-data
description: Ensures ACME Clinical's FastAPI logging and audit trail record only user IDs and record IDs, never passwords, tokens, e-mails or patient health data, using a redacting log filter.
---

# T46: Do not log confidential data

**Category:** CODE_FIX
**SD Elements:** [T46](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T46/)
**Priority:** 4/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A developer would log `request.json()` for observations and login, and include patient name, vitals and the user's e-mail in audit messages for readability. That writes PHI, credentials and PII into Vercel logs and the audit table.

**Secure Implementation Pattern:**
```python
# backend/app/core/logging.py
import logging, re

_REDACT = [
    (re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+"), "[JWT]"),
    (re.compile(r"(?i)(password|token|secret|apikey)\"?\s*[:=]\s*\"?[^\s\",}]+"), r"\1=[REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
]

class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pat, repl in _REDACT:
            msg = pat.sub(repl, msg)
        record.msg, record.args = msg[:2000], ()   # also caps entry length
        return True

def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    logging.basicConfig(level=level, handlers=[handler], force=True)

# Usage: log identifiers, not content
# log.info("observation_created", extra={"user_id": user.id, "patient_id": p.id, "observation_id": o.id})
```

**Implementation Guidance:**
- Log only opaque identifiers: Supabase `auth.users.id` (UUID), `patient_id`, `monitor_id`, `alarm_id`. Never patient names, MRNs, vital values, observation text, e-mails, passwords, JWTs, refresh tokens, password-reset links or signed Storage URLs.
- In `audit_events.details`, store field names changed (e.g. `{"field": "spo2_low", "old": 90, "new": 88}` for thresholds is fine; observation text is not — store `observation_id`).
- Install `RedactingFilter` in `core/logging.py` at app start (`main.py`) as defence in depth; do not rely on it instead of not logging data.
- Never log the `Authorization` header or the Supabase client config; keep debug logging of bodies out of production code entirely (no env-toggled body dumps).
- Frontend: no `console.log` of Supabase session/user objects in `frontend/src/services` and `lib`.
- Reference: SD Elements guidance for T46.

**Success Criteria:**
- [ ] All log/audit calls use IDs only; code review checklist item added.
- [ ] `RedactingFilter` unit test proves JWTs, e-mails and `password=` values are redacted.
- [ ] T229 log-scan test passes.

**Status:** Pending
