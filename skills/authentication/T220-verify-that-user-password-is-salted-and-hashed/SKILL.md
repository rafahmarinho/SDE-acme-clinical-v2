---
name: t220-verify-that-user-password-is-salted-and-hashed
description: Verification test that ACME Clinical staff passwords exist only as unique-salted bcrypt hashes in Supabase auth.users, that app-side password history uses Argon2id, and that no plaintext or weakly hashed password is stored anywhere in the schema or seed, verifying T7.
---

# T220: Verify that user password is salted and hashed

**Category:** CODE_FIX
**SD Elements:** [T220](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T220/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "Entregue o código completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente"
> (EN: Deliver the complete code, database configuration, initial data, environment variable examples)
> Source: specs/PRD.md, lines 45-47

**What the spec implies (naive approach):**
Shipping "dados iniciais" (initial data) tempts developers to add demo users with SQL, using a fixed salt, MD5, or a plaintext password column. This test confirms that only salted slow hashes exist.

**Secure Implementation Pattern:**
```sql
-- supabase/tests/password_storage.test.sql  (pgTAP, run with `supabase test db`)
begin;
select plan(4);

-- 1. every auth password is bcrypt ($2a$/$2b$) with cost >= 10
select is((select count(*) from auth.users
           where encrypted_password is not null
             and encrypted_password !~ '^\$2[aby]\$(1[0-9]|[2-3][0-9])\$'), 0::bigint,
          'all passwords are bcrypt cost>=10');

-- 2. salts are unique (bcrypt salt = chars 8..29)
select is((select count(*) from (select substr(encrypted_password, 8, 22) s
           from auth.users where encrypted_password <> '' group by 1 having count(*) > 1) d),
          0::bigint, 'no shared salts');

-- 3. no password-like columns outside auth/private
select is((select count(*) from information_schema.columns
           where table_schema = 'public' and column_name ilike '%pass%'), 0::bigint,
          'no password columns in public');

-- 4. password history is argon2id only
select is((select count(*) from private.password_history where hash not like '$argon2id$%'),
          0::bigint, 'history uses argon2id');
select * from finish();
rollback;
```

**Implementation Guidance:**
- Code review: confirm that authentication happens only through Supabase Auth (`signInWithPassword`), and that FastAPI never compares passwords except through the GoTrue grant (T3).
- Run the pgTAP test above in CI (`supabase test db`) after migrations and seed.
- Search the repo, including `supabase/seed.sql`, the `.env.example` files and `backend/app/`, for `md5(`, `sha1(`, `hashlib.sha256(password`, `crypt(`, `gen_salt(` and literal passwords. Any hit fails the check unless it is the HIBP prefix lookup (T5).
- A bcrypt salt is 16 bytes (22 base64 characters), which exceeds the 8-byte minimum. Argon2 salts from `argon2-cffi` are 16 random bytes.
- Reference: SD Elements guidance for T220.

**Success Criteria:**
- [ ] All four pgTAP assertions pass in CI.
- [ ] The repository search reports no weak hashing or plaintext password storage.

**Status:** Applied
