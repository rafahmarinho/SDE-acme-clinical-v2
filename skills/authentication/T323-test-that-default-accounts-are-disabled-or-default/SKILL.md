---
name: t323-test-that-default-accounts-are-disabled-or-default
description: Tests that ACME Clinical ships no default credentials: no passwords in seed data, README or env examples, common default passwords fail against demo and admin accounts, demo accounts are disabled in production, and default Supabase local keys are not used in deployed environments, verifying T61.
---

# T323: Test that default accounts are disabled or default passwords are changed

**Category:** CODE_FIX
**SD Elements:** [T323](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T323/)
**Priority:** 9/10 · **Phase:** testing

**Spec Context:**
> "Prepare dados de demonstração com doze pacientes e dez monitores."
> (EN: Prepare demonstration data with twelve patients and ten monitors.)
> Source: specs/PRD.md, line 41

**What the spec implies (naive approach):**
Demo data and "dados iniciais" (initial data) often bring default logins along with them. A later commit could reintroduce `password123` in `seed.sql` or the README, or a deployment could keep the local Supabase demo keys. This test catches both.

**Secure Implementation Pattern:**
```python
# backend/tests/test_no_default_credentials.py
import pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILES = [ROOT / "supabase/seed.sql", ROOT / "README.md",
         *ROOT.glob("**/.env.example"), *ROOT.glob("supabase/migrations/*.sql")]
PATTERNS = [r"crypt\s*\(", r"encrypted_password", r"(?i)password\s*[:=]\s*\S{4,}",
            r"(?i)(admin|demo|test)123", r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.eyJpc3MiOiJzdXBhYmFzZS1kZW1v"]

def test_no_credentials_in_repo_artifacts():
    hits = [(f.name, p) for f in FILES if f.exists()
            for p in PATTERNS if re.search(p, f.read_text(encoding="utf-8"))]
    assert not hits, hits
```
```python
# backend/tests/integration/test_default_passwords.py  (run against the deployed preview)
import pytest
COMMON = ["password", "Password1!", "admin", "Admin123!", "acme123", "Acme@2026", "changeme", "demo"]

@pytest.mark.integration
def test_default_passwords_do_not_work(demo_emails):
    for email in demo_emails:                      # enumerated from profiles via admin API
        for pw in COMMON:
            assert gotrue_login(email, pw).status_code != 200, f"{email} accepts default password"

@pytest.mark.integration
def test_demo_accounts_disabled_in_production(admin_api):
    demo = [u for u in admin_api.list_users() if u.app_metadata.get("demo")]
    assert all(u.banned_until for u in demo)
```

**Implementation Guidance:**
- Third-party defaults: list the defaults (the local Supabase anon and service JWTs with issuer `supabase-demo`, the default `postgres` password, the Studio dashboard). Check that the deployed backend's `SUPABASE_URL` and keys are not the local defaults. A config validator (T230) should reject a JWT whose `iss` is `supabase-demo` when `APP_ENV != local`.
- Application defaults: confirm that no account is created by `seed.sql`, and that demo staff from `create_demo_staff.py` have `must_change_password`.
- Work with whoever operates the hosted Supabase project to confirm that installation-only accounts (for example a bootstrap administrator) are removed or have their credentials rotated after first setup.
- Space out the COMMON password attempts or use dedicated accounts so the lockout (T6) does not interfere. A lockout response also counts as a pass.
- Reference: SD Elements guidance for T323.

**Success Criteria:**
- [ ] The repository scan test passes in CI.
- [ ] No common or default password authenticates any demo or admin account. Demo accounts are banned in production.
- [ ] Deployed environments do not use the Supabase local demo keys.

**Status:** Applied
