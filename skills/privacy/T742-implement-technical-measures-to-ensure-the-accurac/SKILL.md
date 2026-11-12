---
name: t742-implement-technical-measures-to-ensure-the-accurac
description: Keep ACME Clinical personal data accurate - self-service profile editing, strict Pydantic and database validation, one system of record per field (Supabase Auth email mirrored to staff_profiles), and duplicate prevention for staff and patients.
---

# T742: Implement technical measures to ensure the accuracy of personal information

**Category:** CODE_FIX
**SD Elements:** [T742](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T742/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
Patient lists, bed assignments and staff profiles are edited from several screens. Without care, the e-mail is stored both in Supabase Auth and `staff_profiles` and drifts apart, free-text names accept anything, the same patient can be admitted twice, and two patients can end up on one bed - wrong data at the bedside is a patient-safety risk.

**Secure Implementation Pattern:**
```python
# backend/app/schemas/__init__.py
class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: Annotated[str, StringConstraints(min_length=2, max_length=120,
                                                pattern=r"^[\p{L}][\p{L} .'\-]*$")]
```
```sql
-- single source of truth + duplicate prevention
create unique index if not exists staff_email_unique on public.staff_profiles (lower(email));
-- public.patients.bed_id is already "unique" in 0001_schema.sql: one patient per bed
create unique index if not exists patients_active_identity
  on public.patients (lower(display_name), birth_year, ward_id) where discharged_at is null;
-- 0007_privacy.sql: trigger mirrors confirmed Supabase Auth email changes into staff_profiles.email
```

**Implementation Guidance:**
- Self-service: staff review and correct their own name via `PATCH /v1/me` (`backend/app/routers/profile.py`, `frontend/src/screens/Profile.tsx`); e-mail changes go through the confirmed Supabase flow (`double_confirm_changes = true` in `supabase/config.toml`).
- Validate every personal field server-side (Pydantic models in `backend/app/schemas/__init__.py`, helpers in `backend/app/core/validation.py`) and with matching `check` constraints in `supabase/migrations/0001_schema.sql` (T31).
- One system of record: Supabase Auth owns e-mail; the mirror trigger in `supabase/migrations/0007_privacy.sql` propagates confirmed changes to `staff_profiles`; never let the API write `staff_profiles.email` directly.
- Prevent duplicates: canonicalised unique e-mails (`canonical_email` in `backend/app/services/identity.py`), unique bed assignment, and a partial unique index (or explicit duplicate check with a 409) for active patients; add a periodic duplicate report for administrators in `backend/app/services/reports.py`.
- Record who changed what (audit event with field names, not values) so inaccurate edits can be traced.
- Reference: SD Elements guidance for T742.

**Success Criteria:**
- [ ] `backend/tests/test_privacy.py::test_t743_invalid_or_tampered_profile_values_are_rejected` and `test_t743_database_enforces_accuracy_and_consistency` pass.
- [ ] `test_t177_email_change_goes_through_confirmed_supabase_flow` passes.
- [ ] Pytest: creating a second active patient with the same name, birth year and ward returns 409; assigning an occupied bed returns 409.

**Status:** Applied
