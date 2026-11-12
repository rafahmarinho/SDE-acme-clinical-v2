---
name: t4-use-configurable-password-policies
description: Lets ACME Clinical administrators configure the password policy (minimum length, complexity, maximum age, history, banned words and context-specific words) applied to Supabase Auth email/password accounts, enforced in the FastAPI backend and mirrored in the React UI.
---

# T4: Use configurable password policies

**Category:** CODE_FIX
**SD Elements:** [T4](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T4/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
The PRD asks for email/password login on Supabase plus a settings area, so a developer would accept whatever Supabase Auth's default rules allow (a 6-character minimum, no complexity) and would not build any password settings for administrators. The policy would then be fixed and weak, and an administrator could not tighten it for a clinical system.

**Secure Implementation Pattern:**
```python
# backend/app/services/password_policy.py (new module), loaded from table public.password_policy
from pydantic import BaseModel, Field

class PasswordPolicy(BaseModel):
    min_length: int = Field(12, ge=8, le=128)
    max_length: int = Field(128, le=256)
    require_lower: bool = True
    require_upper: bool = True
    require_digit: bool = True
    require_symbol: bool = False
    max_age_days: int | None = Field(None, ge=1)   # None = no forced expiry (NIST)
    history_count: int = Field(5, ge=0, le=24)
    banned_words: list[str] = []                    # admin-maintained dictionary

def violations(pw: str, policy: PasswordPolicy, context: list[str]) -> list[str]:
    errs: list[str] = []
    if not policy.min_length <= len(pw) <= policy.max_length:
        errs.append(f"Password must be {policy.min_length}-{policy.max_length} characters.")
    checks = [(policy.require_lower, str.islower, "a lowercase letter"),
              (policy.require_upper, str.isupper, "an uppercase letter"),
              (policy.require_digit, str.isdigit, "a digit")]
    for on, fn, label in checks:
        if on and not any(fn(c) for c in pw):
            errs.append(f"Password must contain {label}.")
    if policy.require_symbol and pw.isalnum():
        errs.append("Password must contain a symbol.")
    low = pw.lower()
    for word in [*policy.banned_words, "acme", "clinical", *context]:  # context = email local part, name
        if word and len(word) >= 3 and word.lower() in low:
            errs.append("Password contains a forbidden or account-related word.")
            break
    return errs
```

**Implementation Guidance:**
- Add a single-row `public.password_policy` table in `supabase/migrations/0001_schema.sql` with RLS: only the `administrator` role can `update`, and authenticated users can `select` (the UI needs it to show the rules).
- Expose `GET/PUT /admin/password-policy` in a `backend/app/routers/` admin router, protected by the administrator role check in `backend/app/core/security.py`. Validate the body with the `PasswordPolicy` Pydantic model and audit-log every change.
- Route every password set or change (staff invite acceptance, profile password change, reset completion) through a backend endpoint that calls `violations()` before it calls the Supabase Admin API (`auth.admin.update_user_by_id`) with the service role key.
- Also set a matching floor in Supabase itself (`supabase/config.toml` `[auth] minimum_password_length = 12` and `password_requirements = "lower_upper_letters_digits"`, plus the hosted dashboard leaked-password protection). That way a direct GoTrue call cannot go below the floor even though the configurable rules live in the backend.
- Context words: use the email local part, first and last name from `profiles`, and the service name ("acme", "clinical").
- Password history and maximum age: store Argon2 hashes of previous passwords in an RLS-locked table that the client cannot reach, plus `password_changed_at` in `profiles`. Compare the new password against the last `history_count` hashes, and send users whose password is older than `max_age_days` to a forced-change screen.
- Reference: SD Elements guidance for T4.

**Success Criteria:**
- [ ] An administrator can change length, complexity, maximum age, history count and banned words from the Settings screen. A non-administrator gets 403 from `PUT /admin/password-policy`.
- [ ] `backend/tests/test_password_policy.py` checks that changing `min_length` from 12 to 16 makes a 14-character password fail on the next change, and that passwords containing the user's email local part are rejected.
- [ ] Supabase `minimum_password_length` is at least 12 in `supabase/config.toml`.

**Status:** Pending
