---
name: t286-make-sure-username-rules-are-consistent-among-the
description: Defines one canonical email (username) rule for ACME Clinical shared by the React login form, the FastAPI team-management API, Supabase Auth and the profiles table, so variants differing in case, whitespace or Unicode never map to a different identity.
---

# T286: Make sure username rules are consistent among the registration system, authentication system, and application

**Category:** CODE_FIX
**SD Elements:** [T286](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T286/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e senha"
> (EN: Use current, stable technologies and Supabase for PostgreSQL, email and password login)
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
Staff are registered by the backend (team management), authenticated by Supabase GoTrue, and authorized by the app through `profiles`. Three subsystems handling the same email string differently (GoTrue lowercases, the backend does not trim, the UI does both) can lead to duplicate accounts or role confusion.

**Secure Implementation Pattern:**
```python
# backend/app/services/identity.py
import unicodedata
from pydantic import BaseModel, EmailStr, field_validator

def canonical_email(raw: str) -> str:
    if raw != raw.strip() or any(unicodedata.category(c) in ("Cf", "Zs", "Cc") for c in raw):
        raise ValueError("Email must not contain spaces or invisible characters")
    value = unicodedata.normalize("NFKC", raw).lower()
    if not value.isascii():
        raise ValueError("Only ASCII email addresses are accepted")
    return value

class StaffCreate(BaseModel):
    email: EmailStr
    full_name: str
    role: str
    employee_number: str

    @field_validator("email", mode="before")
    @classmethod
    def _canon(cls, v: str) -> str:
        return canonical_email(v)
```
```sql
-- supabase/migrations/0001_schema.sql: DB enforces the same rule
alter table public.profiles add constraint profiles_email_canonical
  check (email = lower(email) and email = btrim(email) and email ~ '^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$');
```
```typescript
// frontend/src/lib/identity.ts - same rule before signInWithPassword / resetPasswordForEmail
export const canonicalEmail = (raw: string) => raw.normalize('NFKC').trim().toLowerCase();
```

**Implementation Guidance:**
- Write down the rule in the README: emails are ASCII and stored lowercase; leading or trailing whitespace is trimmed in the UI but rejected by the API; invisible characters are rejected.
- Registration (`POST /admin/staff`) uses `StaffCreate`. Authentication (frontend login and reset) uses `canonicalEmail`. GoTrue lowercases emails as well. The DB check constraint is the final guard.
- Authorization keys on `auth.uid()` / `claims["sub"]`, never on the email text, so email changes (T517) cannot remap identities.
- Make sure that no two valid inputs collapse to one stored value after normalization without being treated as the same account (unique index on `lower(email)`, T135).
- Reference: SD Elements guidance for T286.

**Success Criteria:**
- [ ] One rule is documented and implemented identically in `identity.py`, `identity.ts` and the DB constraint.
- [ ] Unit tests in `backend/tests/test_identity.py` and `frontend/src/lib/identity.test.ts` cover case, whitespace, zero-width and full-width variants.

**Status:** Applied
