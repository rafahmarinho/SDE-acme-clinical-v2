---
name: t80-test-password-requirements
description: Security tests verifying that ACME Clinical rejects password changes that violate the configured policy (length, complexity, dictionary/breached words, reuse, expiry), at both the FastAPI backend and Supabase Auth level.
---

# T80: Test password requirements

**Category:** CODE_FIX
**SD Elements:** [T80](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T80/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Password rules might exist only as hints in the UI, or only in the backend, while Supabase GoTrue still accepts 6-character passwords through direct API calls. Without tests, weak passwords and reuse would quietly be allowed again.

**Secure Implementation Pattern:**
```python
# backend/tests/test_password_requirements.py
import pytest
from app.services.password_policy import PasswordPolicy, violations, matches_history_any

POLICY = PasswordPolicy(min_length=12, require_lower=True, require_upper=True,
                        require_digit=True, history_count=5, banned_words=["acme", "clinical"])

@pytest.mark.parametrize("pw", [
    "Short1a",                 # too short
    "alllowercase1234",        # no upper
    "ALLUPPERCASE1234",        # no lower
    "NoDigitsHereAtAll",       # no digit
    "AcmeClinical2026",        # banned / context word
    "Nurse.Demo12345",         # contains email local part
])
def test_policy_rejects(pw):
    assert violations(pw, POLICY, context=["nurse.demo", "nurse", "demo"])

def test_policy_accepts_strong():
    assert not violations("Violet-Harbor-Lantern-82", POLICY, context=["nurse.demo"])

def test_reuse_blocked(history_hashes_for_last_5):
    assert matches_history_any("Previous-Password-01", history_hashes_for_last_5)

def test_expired_password_forces_change(client_with_expired_user):
    r = client_with_expired_user.get("/me")
    assert r.json()["password_change_required"] is True
```

**Implementation Guidance:**
- Unit: cover each rule in `backend/app/services/password_policy.py` (T4 and T5) with the tests above, including the HIBP check mocked with respx.
- API: call `POST /me/password` with each weak password and expect 422. Reuse of any of the last 5 passwords must also give 422.
- Platform floor: against local `supabase start`, call `supabase.auth.updateUser({ password: 'abc123' })` directly and expect GoTrue to reject it (minimum length and `password_requirements` in `supabase/config.toml`).
- Expiry (if `max_age_days` is set): set `password_changed_at` past the limit and check that the user is forced to change the password before any patient data loads.
- Compliance review: record the chosen policy in the README and compare it with the organization's policy and HIPAA-aligned guidance. Fail if the policy is weaker.
- Reference: SD Elements guidance for T80.

**Success Criteria:**
- [ ] All parametrized weak passwords are rejected and the strong one is accepted in CI.
- [ ] A direct GoTrue call with a 6-character password fails in the local Supabase integration test.
- [ ] Password reuse and expiry behavior is covered by tests.

**Status:** Pending
