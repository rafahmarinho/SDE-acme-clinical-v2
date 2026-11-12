---
name: t7-salt-and-hash-stored-passwords
description: Ensures ACME Clinical never stores staff passwords itself, delegating storage to Supabase Auth (salted bcrypt), and that any app-side password material such as password history uses a salted slow hash (Argon2id).
---

# T7: Salt and hash stored passwords

**Category:** CODE_FIX
**SD Elements:** [T7](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T7/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e senha"
> (EN: Use current, stable technologies and Supabase for PostgreSQL, email and password login)
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
Supabase Auth already stores salted bcrypt hashes in `auth.users.encrypted_password`. The risk is in app code: a developer building "gestão da equipe" (team management) or demo seed data might add a `password` column to `public.profiles`, keep a plaintext temporary password, or write password history with a fast unsalted SHA-256.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py - only for app-side password history (T4/T5), never for login
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)  # Argon2id, random 16-byte salt per hash

def hash_for_history(password: str) -> str:
    return _ph.hash(password)               # encoded string carries algorithm, params and unique salt

def matches_history(password: str, encoded: str) -> bool:
    try:
        return _ph.verify(encoded, password)
    except VerifyMismatchError:
        return False
```
```sql
-- supabase/migrations/0001_schema.sql: history is unreachable from PostgREST
create table private.password_history (
  user_id uuid references auth.users(id) on delete cascade,
  hash text not null check (hash like '$argon2id$%'),
  created_at timestamptz not null default now()
);
revoke all on private.password_history from anon, authenticated;
```

**Implementation Guidance:**
- Authenticate only through Supabase Auth (`signInWithPassword`). Never implement password checks in FastAPI or keep password columns in `public` tables.
- Do not insert rows into `auth.users` with `crypt('...', gen_salt('bf'))` in `supabase/seed.sql` to make demo logins. Create demo staff through the Admin API instead (see T61).
- Use a field-tested library (`argon2-cffi`) for any app-side hash. Do not hand-roll hashing and do not use SHA-1, MD5 or unsalted SHA-2.
- Keep `private` schema tables out of `[api] schemas` in `supabase/config.toml`, so they are not exposed through the Data API.
- Because slow hashing costs CPU, rate-limit the backend password-change endpoint (T6) to avoid DoS.
- Reference: SD Elements guidance for T7.

**Success Criteria:**
- [ ] No table in the `public` schema has a column named like `%password%` (checked by a migration test).
- [ ] `backend/tests/test_hashing.py` checks that two hashes of the same password differ (unique salt), start with `$argon2id$`, and verify correctly.
- [ ] `supabase/seed.sql` contains no `crypt(`, `encrypted_password` or plaintext passwords.

**Status:** Pending
