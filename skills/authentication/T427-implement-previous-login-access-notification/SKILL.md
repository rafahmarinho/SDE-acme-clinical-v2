---
name: t427-implement-previous-login-access-notification
description: Shows ACME Clinical staff details of their previous logins (date, time, approximate location, device) and the number of failed attempts since the last success after they sign in, and notifies them of security-relevant account changes.
---

# T427: Implement previous login (access) notification

**Category:** CODE_FIX
**SD Elements:** [T427](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T427/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
After login, the user goes straight to the ward overview with no information about earlier access. A nurse whose shared-workstation password was compromised would not notice logins they did not make, or a run of failed attempts.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql
create table private.login_events (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  success boolean not null,
  ip inet, user_agent text, country text,
  created_at timestamptz not null default now()
);
create index on private.login_events (user_id, created_at desc);
-- failures are recorded by the password-verification hook (T6):
--   insert into private.login_events(user_id, success) values (uid, (event->>'valid')::boolean);
```
```python
# backend/app/routers/profile.py
@router.post("/me/session-start")
async def session_start(request: Request, claims=Depends(verify_supabase_jwt)):
    uid = claims["sub"]
    prev = await db.fetch("""select created_at, ip, user_agent, country from private.login_events
                             where user_id=$1 and success order by created_at desc limit $2""",
                          uid, settings.previous_logins_shown)          # configurable, e.g. 5
    failed = await db.fetchval("""select count(*) from private.login_events where user_id=$1
        and not success and created_at > coalesce((select max(created_at) from private.login_events
        where user_id=$1 and success), '-infinity')""", uid)
    await db.execute("insert into private.login_events(user_id,success,ip,user_agent,country) "
                     "values ($1,true,$2,$3,$4)", uid, client_ip(request),
                     request.headers.get("user-agent", "")[:200],
                     request.headers.get("x-vercel-ip-country"))
    return {"previous_logins": prev, "failed_since_last_login": failed}
```

**Implementation Guidance:**
- The frontend calls `POST /me/session-start` once after the Supabase `SIGNED_IN` event (in `frontend/src/hooks/`) and shows a dismissible banner, for example "Last sign-in: 11 Nov 2026 07:02 from Chrome, BR. 3 failed attempts since." Include a "This wasn't me" link that signs out all sessions and starts a password reset.
- Location comes from the Vercel `x-vercel-ip-country`/`-city` headers. Store only the coarse location, and apply a retention period (for example 90 days) for privacy.
- Security-change notifications (password changed, email changed, MFA factor added or removed, role changed) go to the user's verified email through the simulated email service and appear in an in-app list. They do not wait for the next login.
- Keep `private.login_events` out of the Data API. Users read their own history only through the backend.
- Reference: SD Elements guidance for T427.

**Success Criteria:**
- [ ] After login, the banner shows the last N successful logins (date, time, location, device) and the count of failed attempts since the last success. N is configurable.
- [ ] Password, email, MFA and role changes trigger a notification to the user's email (`backend/tests/test_login_notifications.py`).

**Status:** Applied
