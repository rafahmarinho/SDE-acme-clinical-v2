---
name: t604-implement-a-consent-withdrawal-mechanism
description: Let ACME Clinical staff see every consent they have given and withdraw each one from the Profile privacy page, with withdrawal recorded, audited and immediately stopping the processing that depended on it.
---

# T604: Implement a consent withdrawal mechanism

**Category:** CODE_FIX
**SD Elements:** [T604](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T604/)
**Priority:** 10/10 · **Phase:** requirements

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: services and database access. Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Once consent is collected (T178) a naive app offers no way back, or a "withdraw" toggle only hides the setting in the UI while background jobs keep using the data (e.g. still sending escalation SMS or recording login locations).

**Secure Implementation Pattern:**
```python
# backend/app/routers/profile.py
@router.get("/consents", response_model=list[ConsentOut])
async def list_consents(principal: Principal = Depends(require(Perm.profile_self))): ...

@router.delete("/consents/{purpose}", status_code=204)
async def withdraw(purpose: ConsentPurpose, request: Request,
                   principal: Principal = Depends(require(Perm.profile_self))):
    async with transaction() as conn:
        n = await conn.execute(
            """update public.consent_grants set withdrawn_at = now()
               where user_id = %s and purpose = %s and withdrawn_at is null""",
            (principal.user_id, purpose))
        await stop_processing(conn, principal.user_id, purpose)      # disable dependent features now
        await record_event(principal, "consent_withdrawn", "staff_profile", str(principal.user_id),
                           outcome="success", details={"purpose": purpose}, request_id=request.state.request_id)

# every consumer checks before acting
if not await consent_service.has(conn, user_id, "alarm_sms_escalation"):
    return   # skip, do not queue
```

**Implementation Guidance:**
- Add `GET /v1/me/consents` and `DELETE /v1/me/consents/{purpose}` in `backend/app/routers/profile.py`, backed by the `consent_grants` table from T178 (`withdrawn_at` column; history kept as evidence).
- In `frontend/src/screens/Profile.tsx` (`PrivacyPage`), fetch and list each active consent with a toggle to withdraw; confirm and show the effective date.
- `stop_processing` disables dependent features immediately (e.g. clears an escalation phone from active routing, stops login-location capture). Withdrawal does not by itself delete historic data; deletion is the erasure flow (`POST /v1/me/erasure-request`, T179/T607).
- Every consumer of consent-based data calls `consent_service.has()` at time of use, not a cached flag.
- Inform processors (e.g. SMS provider) when a withdrawal affects them; document in `docs/security/privacy.md`.
- Include consents and withdrawals in the personal-data export (`GET /v1/me/export`).
- Reference: SD Elements guidance for T604.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_privacy.py`): after `DELETE /v1/me/consents/{purpose}`, `consent_service.has()` is false and the dependent action is skipped.
- [ ] Pytest: withdrawal is audited, keeps the original grant row and sets `withdrawn_at`; a user cannot withdraw another user's consent.
- [ ] Vitest: the privacy page lists active consents and calls the DELETE endpoint when a toggle is switched off.
- [ ] The export includes consent history.

**Status:** Pending
