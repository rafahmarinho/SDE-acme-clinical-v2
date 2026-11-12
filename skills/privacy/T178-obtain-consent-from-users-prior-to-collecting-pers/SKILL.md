---
name: t178-obtain-consent-from-users-prior-to-collecting-pers
description: Obtain explicit, granular, opt-in consent from ACME Clinical staff users before any optional collection of their personal information (beyond what clinical operation requires), separate from the privacy-notice acknowledgement, and store versioned evidence of each consent.
---

# T178: Obtain consent from users prior to collecting personal information

**Category:** CODE_FIX
**SD Elements:** [T178](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T178/)
**Priority:** 10/10 · **Phase:** requirements

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: services and database access. Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A "profile" and "settings" area naturally collects extra staff data (phone number for alarm escalation, photo, login-location history, usage analytics). A naive build stores these as soon as the user types them, or pre-ticks "I agree" inside the terms screen, with no record of which purposes were accepted or under which notice version.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0009_consent_items.sql
create table public.consent_purposes (
  code text primary key check (code ~ '^[a-z_]{3,40}$'),   -- e.g. 'alarm_sms_escalation', 'login_location'
  notice_version text not null, required boolean not null default false,
  description text not null
);
create table public.consent_grants (
  user_id uuid not null references public.staff_profiles(user_id) on delete cascade,
  purpose text not null references public.consent_purposes(code),
  notice_version text not null, language text not null default 'en',
  granted_at timestamptz not null default now(), withdrawn_at timestamptz,
  evidence jsonb not null,                                  -- session id, request id, UI version
  primary key (user_id, purpose, granted_at)
);
alter table public.consent_grants enable row level security;
create policy consent_own on public.consent_grants for select to acme_api_rw using (user_id = public.current_staff_id());
```
```python
# backend/app/routers/profile.py
@router.post("/consents", status_code=204)
async def grant(body: ConsentIn, principal: Principal = Depends(require(Perm.profile_self))):
    # body.purposes is an explicit list; nothing is granted by default
    await consent_service.grant(principal, body.purposes, body.notice_version, request_ctx())
```

**Implementation Guidance:**
- With the privacy officer, list every staff data item and mark which are necessary for clinical operation (lawful basis other than consent, already covered by the privacy notice in `backend/app/services/privacy.py` `PRIVACY_NOTICE` and `public.privacy_consents`) and which are optional and require consent; record this in `docs/security/privacy.md` / PIA.
- Keep consent separate from the privacy-notice acknowledgement (`POST /v1/me/privacy-notice`): add purpose-level consent tables (migration `0009`) and endpoints in `backend/app/routers/profile.py`.
- UI (`frontend/src/screens/Profile.tsx` `PrivacyPage`): unchecked toggles per purpose, each with purpose, data categories, retention, withdrawal method and third parties; visible Accept / Decline buttons; required vs optional fields marked with tooltips.
- Gate collection: services that store optional data (`backend/app/services/*`) call `consent_service.has(user, purpose)` and refuse (409) without an active grant.
- Store evidence: purpose, notice version, language, user id, session/request id and timestamp; audit `consent_granted` via `backend/app/core/audit.py`.
- A new purpose or a new notice version requires a new grant.
- Patient data is fictional demo data processed for care, not on consent (`PRIVACY_NOTICE` states this); do not apply this flow to patients.
- Reference: SD Elements guidance for T178.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_privacy.py`): saving an optional field without a grant returns 409; after `POST /v1/me/consents` it succeeds.
- [ ] Pytest: a grant row stores purpose, notice version, language, timestamp and request id, and an audit event is written.
- [ ] Vitest (`frontend/src/screens/Profile.test.tsx`): all consent toggles render unchecked and Accept/Decline buttons are visible.
- [ ] Pytest: RLS prevents one user reading another user's consent grants.

**Status:** Pending
