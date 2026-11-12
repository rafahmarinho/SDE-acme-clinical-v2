---
name: t229-verify-that-logs-do-not-contain-confidential-data
description: Test that ACME Clinical backend logs, Vercel runtime logs and the audit table never contain passwords, JWTs, Supabase keys or patient health data (vital signs, names, observations).
---

# T229: Verify that logs do not contain confidential data

**Category:** CODE_FIX
**SD Elements:** [T229](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T229/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "Use pacientes fictícios e monitores simulados para mostrar"
> (EN: Use fictional patients and simulated monitors to show)
> Source: specs/PRD.md, line 29

> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current, stable technology versions and Supabase for PostgreSQL, email and password login)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
Because the patients are fictional, developers tend to log full request bodies, observation text and vital-sign payloads, plus `Authorization` headers when debugging Supabase Auth. The same code would leak protected health information and tokens once used with real data.

**Secure Implementation Pattern:**
```python
# backend/tests/test_log_confidentiality.py
import logging, re, pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

SECRET_PATTERNS = [
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT
    re.compile(r"(?i)password"), re.compile(r"(?i)service_role"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                             # e-mail
]

@pytest.mark.asyncio
async def test_no_confidential_data_in_logs(caplog, nurse_token, demo_patient):
    caplog.set_level(logging.DEBUG)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h = {"Authorization": f"Bearer {nurse_token}"}
        await c.post("/observations", headers=h,
                     json={"patient_id": demo_patient.id, "text": "Patient reports chest pain"})
        await c.post("/auth/login", json={"email": "nurse@acme.test", "password": "Wrong-Pass-1"})
    text = caplog.text
    assert "chest pain" not in text and demo_patient.name not in text
    for p in SECRET_PATTERNS:
        assert not p.search(text), p.pattern

def test_production_log_level(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    from app.core.config import Settings
    assert Settings().log_level in ("INFO", "WARNING", "ERROR")
```

**Implementation Guidance:**
- List the confidential data for this app: passwords, Supabase JWTs/refresh tokens, `SUPABASE_SERVICE_ROLE_KEY`, user e-mails, patient names, vital-sign values, observation text, signed Storage URLs.
- Add the pytest above under `backend/tests/` exercising login, password recovery, observations, threshold changes and file upload endpoints, scanning `caplog` and the `audit_events.details` column.
- Code review: grep `backend/app` for `logger.*(request.headers|body|password|token)` and `print(`; review `frontend/src/services` for `console.log` of sessions.
- Manual check: pull Vercel runtime logs for the API after a demo run and search for the same patterns.
- Confirm DEBUG is disabled in production config (`core/config.py`).
- Reference: SD Elements guidance for T229.

**Success Criteria:**
- [ ] Pytest scanning captured logs and audit rows passes with zero matches.
- [ ] Production `log_level` is INFO or higher, asserted by a test.
- [ ] A manual review of Vercel runtime logs after a demo run is documented with no findings.

**Status:** Pending
