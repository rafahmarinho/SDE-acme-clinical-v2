---
name: t25-enforce-absolute-session-timeouts
description: Enforce an absolute lifetime on ACME Clinical sessions (default one 12-hour clinical shift) regardless of activity, both in FastAPI and in Supabase Auth settings, with an advance warning to the user.
---

# T25: Enforce absolute session timeouts

**Category:** CODE_FIX
**SD Elements:** [T25](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T25/)
**Priority:** 3/10 · **Phase:** requirements

**Spec Context:**
> "Os resultados"
> "devem aparecer nas telas e continuar salvos após recarregar a aplicação."
> (EN: The results must appear on the screens and remain saved after reloading the application.)
> Source: specs/PRD.md, lines 43-45

**What the spec implies (naive approach):**
"Remain saved after reloading" refers to *data* persisted in Supabase PostgreSQL (simulation results, observations, alarm acknowledgements), not to the login session. A developer may still read it as "keep the user logged in", and since Supabase refresh tokens rotate indefinitely by default, a session that keeps refreshing would never end: one login could last weeks on a ward PC.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
async def require_session(claims: Claims = Depends(verify_supabase_jwt), db=Depends(get_db)) -> Session:
    sess = await load_app_session(db, claims.session_id)
    if sess is None or sess.revoked_at is not None:
        raise HTTPException(401, detail={"error": "session_revoked"})
    max_age = timedelta(hours=min(sess.user_absolute_hours or settings.absolute_timeout_hours, 12))
    expires_at = sess.created_at + max_age
    if datetime.now(timezone.utc) >= expires_at:
        await revoke_session(db, sess.session_id, reason="absolute_timeout")
        raise HTTPException(401, detail={"error": "session_expired"})
    request_state_set_expiry(expires_at)        # middleware adds X-Session-Expires-At header
    return sess
```
```typescript
// frontend/src/hooks/useSessionExpiryWarning.ts
// read X-Session-Expires-At from API responses; 10 minutes before -> toast
// "Your session ends at 19:00. Save your observation and sign in again."; at expiry -> logout("absolute")
```

**Implementation Guidance:**
- Default absolute lifetime: 12 hours (one clinical shift), hard maximum 12 hours for clinical roles and 8 hours for administrators; well under the SD Elements one-week ceiling, as this is a critical application. Users may *shorten* their own value in Settings (stored per user); they may never extend beyond the cap.
- Compute expiry from `app_sessions.created_at` (set at `POST /auth/session`, see T429), never from the access JWT `iat`, because each refresh issues a new JWT.
- Also enable Supabase Auth "Time-boxed user sessions" (session timebox = 12h) and keep the access-token expiry short, so direct Supabase/Realtime access ends too; RLS helper `app_session_active()` (T26) can additionally check `created_at`.
- Return the expiry in a response header (`X-Session-Expires-At`, exposed via CORS `expose_headers`) and warn the user 10 minutes before so unsaved observations are not lost.
- On expiry, run the normal logout routine (T26/T1540) and show "Your session has expired, please sign in again".
- Reference: SD Elements guidance for T25.

**Success Criteria:**
- [ ] A session older than the configured absolute limit is rejected with `401 session_expired` even while continuously active.
- [ ] Refreshing the token does not extend the absolute lifetime.
- [ ] Users see a warning before expiry and can only lower their own limit.
- [ ] Tests in `backend/tests/test_absolute_timeout.py` (see T92).

**Status:** Pending
