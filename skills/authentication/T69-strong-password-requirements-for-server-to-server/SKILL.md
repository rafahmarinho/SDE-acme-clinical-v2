---
name: t69-strong-password-requirements-for-server-to-server
description: Require every ACME Clinical system credential (Supabase service role key, JWT secret, database role password, monitor device secrets, audit signing and HMAC keys) to meet at least the end-user password policy, and refuse to start with weak or placeholder values.
---

# T69: Strong password requirements for server-to-server system accounts

**Category:** CODE_FIX
**SD Elements:** [T69](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T69/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: complete [code], database configuration, initial data, environment variable examples and a)
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
Shipping "environment variable examples" and a "database configuration" often ends with a short database password such as `postgres`, a copied example secret, or one short shared secret for all simulated monitors. These system accounts are never typed by a person, so nobody notices they are far weaker than the 12-character staff password policy.

**Secure Implementation Pattern:**
```python
# backend/app/services/passwords.py
def system_secret_problems(name: str, value: str, *, min_length: int = 16) -> list[str]:
    problems = []
    if len(value) < max(min_length, PLATFORM_MIN_LENGTH):
        problems.append(f"{name} shorter than {min_length} characters")
    if value.startswith("<") or value.lower() in COMMON_PASSWORDS or _is_repetitive_or_sequential(value):
        problems.append(f"{name} is a placeholder or guessable value")
    return problems

# backend/app/core/config.py
@model_validator(mode="after")
def _production_secret_strength(self) -> "Settings":
    if not self.is_production:
        return self
    problems = database_url_problems(self.database_url.get_secret_value())
    problems += system_secret_problems("SUPABASE_SERVICE_ROLE_KEY", self.supabase_service_role_key.get_secret_value())
    problems += system_secret_problems("SUPABASE_JWT_SECRET", self.supabase_jwt_secret.get_secret_value(), min_length=32)
    if self.config_integrity_key is not None:      # also AUDIT_SIGNING_KEY presence/format
        problems += system_secret_problems("CONFIG_INTEGRITY_KEY",
                                           self.config_integrity_key.get_secret_value(), min_length=32)
    if problems:
        raise ValueError("insecure production configuration: " + "; ".join(problems))
    return self
```

**Implementation Guidance:**
- Keep one rule set: system secrets are checked by `system_secret_problems` / `database_url_problems` in `backend/app/services/passwords.py`, whose floor is never lower than the end-user policy (`PasswordPolicy`, `supabase/config.toml` `minimum_password_length = 12`).
- Validate at startup in `backend/app/core/config.py` (`_production_secret_strength`, `_not_empty_or_placeholder`) so a weak `SUPABASE_JWT_SECRET`, HMAC key or database password in Vercel environment variables blocks deployment.
- Monitor device secrets are generated per device by `python -m app.cli provision-monitor-secrets` (`backend/app/cli.py`, `new_device_secret` in `backend/app/services/device_auth.py`) with `secrets`; never use a shared or role-named secret; `verify_monitor_secret` in `0006_auth.sql` rejects secrets shorter than 16 characters.
- The database login role used by the API (`acme_api` / `DATABASE_URL`) gets a randomly generated password of 32+ characters set in the Supabase dashboard; document rotation in `docs/security/secure-config.md`.
- `backend/.env.example` holds placeholders only (`<...>`), which must fail validation.
- Reference: SD Elements guidance for T69.

**Success Criteria:**
- [ ] `backend/tests/test_authentication.py::test_weak_system_secrets_rejected` covers short, common, sequential and placeholder values for every system secret.
- [ ] `test_env_examples_do_not_pass_secret_validation` confirms the example files cannot be used as real secrets.
- [ ] Pytest: production `Settings` with a 20-character JWT secret raises a validation error; a 48-character random value passes.
- [ ] Device secrets issued by the CLI are unique per monitor and at least 32 characters.

**Status:** Applied
