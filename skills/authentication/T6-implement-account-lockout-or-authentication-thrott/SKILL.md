---
name: t6-implement-account-lockout-or-authentication-thrott
description: Adds brute-force protection to ACME Clinical's Supabase email/password login through a Supabase password-verification-attempt hook (soft lockout), CAPTCHA and Auth rate limits, while keeping administrator hard locks (bans) separate.
---

# T6: Implement account lockout or authentication throttling

**Category:** CODE_FIX
**SD Elements:** [T6](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T6/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e senha, arquivos e atualizações em tempo real."
> (EN: Use current, stable technologies and Supabase for PostgreSQL, email and password login, files and real-time updates.)
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
The login screen would call `supabase.auth.signInWithPassword()` directly and rely on Supabase defaults. Those limit requests per IP, but nothing counts failures per account, so a distributed attacker can keep guessing a nurse's password without limit.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql
create table private.auth_failures (
  user_id uuid primary key references auth.users(id) on delete cascade,
  failures int not null default 0,
  locked_until timestamptz
);

create or replace function public.hook_password_verification_attempt(event jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare uid uuid := (event->>'user_id')::uuid; rec private.auth_failures;
begin
  select * into rec from private.auth_failures where user_id = uid;
  if rec.locked_until is not null and rec.locked_until > now() then
    return jsonb_build_object('decision','reject',
      'message','Invalid login credentials','should_logout_user', false);
  end if;
  if (event->>'valid')::boolean then
    delete from private.auth_failures where user_id = uid;
  else
    insert into private.auth_failures as f (user_id, failures) values (uid, 1)
    on conflict (user_id) do update set failures = f.failures + 1,
      locked_until = case when f.failures + 1 >= 5   -- exponential soft lock
        then now() + make_interval(mins => least(60, power(2, f.failures + 1 - 5)::int * 5)) end;
  end if;
  return jsonb_build_object('decision','continue');
end $$;

grant usage on schema private to supabase_auth_admin;
grant all on private.auth_failures to supabase_auth_admin;
grant execute on function public.hook_password_verification_attempt to supabase_auth_admin;
revoke execute on function public.hook_password_verification_attempt from authenticated, anon, public;
```

**Implementation Guidance:**
- Register the hook in `supabase/config.toml` (`[auth.hook.password_verification_attempt] enabled = true`, `uri = "pg-functions://postgres/public/hook_password_verification_attempt"`) and in the hosted project's Auth Hooks settings. Check that your Supabase plan includes this hook. If it does not, rely on CAPTCHA and rate limits and document the residual risk.
- Soft lock: 5 failures trigger a 5-minute lock, doubling up to 60 minutes. The reject message stays the generic "Invalid login credentials" (T8).
- Hard lock: administrators ban accounts through the backend team-management endpoint (`auth.admin.update_user_by_id(uid, {"ban_duration": "876000h"})`). The soft-lock table never clears or overrides a ban.
- Anti-automation and DoS: enable CAPTCHA (`[auth.captcha] enabled = true`, provider `turnstile` or `hcaptcha`), pass `options.captchaToken` from `frontend/src/screens/Login`, and tighten `[auth.rate_limit]` sign-in and email values.
- Give administrators an "unlock" action that deletes the `private.auth_failures` row and audit-logs it.
- Reference: SD Elements guidance for T6.

**Success Criteria:**
- [ ] Six consecutive wrong passwords for one account give a generic failure, and the correct password is rejected until the lock expires.
- [ ] A soft-lock expiry never lifts an administrator ban (`banned_until` stays set).
- [ ] Integration test `backend/tests/test_lockout.py` (run against local `supabase start`) covers the soft lock, its expiry and admin unlock. A CAPTCHA token is required on the login form.

**Status:** Applied
