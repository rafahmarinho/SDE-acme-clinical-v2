---
name: t24-enforce-idle-session-timeout
description: Lock ACME Clinical sessions on shared ward workstations after a configurable period of user inactivity (default 15 minutes), enforced both in the React SPA and server-side in FastAPI, and require re-authentication to unlock.
---

# T24: Enforce idle session timeout

**Category:** CODE_FIX
**SD Elements:** [T24](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T24/)
**Priority:** 3/10 · **Phase:** requirements

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
The live monitoring screen streams vitals via Supabase Realtime and `supabase-js` refreshes the token automatically in the background, so a session left open on a ward workstation never ends. Live updates and token refreshes look like activity, so Supabase's own refresh-based inactivity setting would never trigger. Anyone walking up to the workstation inherits the nurse's or physician's access to patients, alarms and thresholds.

**Secure Implementation Pattern:**
```typescript
// frontend/src/hooks/useIdleLock.ts
const EVENTS = ["pointerdown", "keydown", "wheel", "touchstart"] as const;

export function useIdleLock(idleMs: number, onLock: () => void) {
  useEffect(() => {
    let timer = window.setTimeout(onLock, idleMs);
    let lastBeat = 0;
    const activity = () => {
      clearTimeout(timer);
      timer = window.setTimeout(onLock, idleMs);
      if (Date.now() - lastBeat > 60_000) {           // throttle server heartbeat
        lastBeat = Date.now();
        api.post("/auth/heartbeat").catch(() => {});
      }
    };
    EVENTS.forEach((e) => window.addEventListener(e, activity, { passive: true }));
    return () => { clearTimeout(timer); EVENTS.forEach((e) => window.removeEventListener(e, activity)); };
  }, [idleMs, onLock]);
}
// onLock: supabase.auth.stopAutoRefresh(); removeAllChannels(); clear query cache; show <LockScreen/>
```
```python
# backend/app/core/security.py (inside the session dependency)
idle = timedelta(minutes=settings.idle_timeout_minutes)          # default 15, max 30
if now - sess.last_activity_at > idle:
    await revoke_session(db, sess.session_id, reason="idle_timeout")
    raise HTTPException(401, detail={"error": "session_idle"})
```

**Implementation Guidance:**
- Choose the period with clinical stakeholders: default 15 minutes for nurse/physician/technician, 10 for administrator; allow an administrator to set 5-30 minutes in Settings ("configurações"), stored in a `security_settings` table and read by `backend/app/core/config.py`. Never allow "disabled".
- Only *real user input* counts as activity: Realtime messages, polling and automatic token refreshes must not reset the timer.
- Client side (`frontend/src/hooks/useIdleLock.ts`, mounted in the app shell): on timeout, stop auto refresh, remove Realtime channels, clear in-memory patient data and render a full-screen lock that hides all patient information. Unlocking requires the password again (`signInWithPassword`), which creates a new session; then call `POST /auth/session`.
- Synchronise across tabs with a `BroadcastChannel("acme-idle")` so activity in one tab keeps the others alive and a lock in one tab locks all.
- Server side (`backend/app/core/security.py`): `POST /auth/heartbeat` updates `app_sessions.last_activity_at`; every request checks the idle window and revokes the session (including the `auth.sessions` row) when exceeded, so a token from an unattended workstation stops working server-side even if the client-side lock is bypassed (for example by editing JavaScript or replaying the token with curl).
- If a dedicated wall-mounted central monitoring display is required, treat it as a separate, explicitly provisioned read-only account/role decision; do not weaken the timeout for normal clinical accounts.
- Reference: SD Elements guidance for T24.

**Success Criteria:**
- [ ] After the configured idle period without input, the UI locks and no patient data is visible or reachable.
- [ ] The API returns `401 session_idle` for the old token after the idle window, even if Realtime traffic continued.
- [ ] Unlock requires password re-entry; the old refresh token is unusable.
- [ ] Tests: `frontend/src/hooks/useIdleLock.test.ts` (vitest fake timers) and `backend/tests/test_idle_timeout.py` (see T90).

**Status:** Applied
