---
name: t743-verify-accuracy-of-personal-information
description: Test recipe verifying ACME Clinical keeps staff and patient personal data accurate through editable profiles, Pydantic validation and database consistency checks on profiles, patients and observations.
---

# T743: Verify accuracy of personal information

**Category:** CODE_FIX
**SD Elements:** [T743](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T743/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow linking a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Observations, patient details and staff profiles will be free-text inputs saved as-is. Without validation and consistency checks, a monitor can be linked to two beds, an observation can be attached to a discharged patient, and malformed phone/email values persist, making clinical records inaccurate.

**Secure Implementation Pattern:**
```python
# backend/tests/test_data_accuracy.py
import pytest

@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"full_name": "", "current_password": "x"},
    {"full_name": "A" * 500, "current_password": "x"},
    {"phone": "call me", "full_name": "Sam", "current_password": "x"},
])
async def test_profile_validation_rejects_bad_values(client, nurse, payload):
    r = await client.patch("/me", headers=auth(nurse.token), json=payload)
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_observation_requires_admitted_patient(client, nurse, discharged_patient):
    r = await client.post(f"/patients/{discharged_patient.ref}/observations",
                          headers=auth(nurse.token), json={"text": "BP stable"})
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_monitor_single_bed_constraint(db, monitor, bed_a, bed_b):
    await db.execute("insert into bed_assignments(monitor_id, bed_id) values ($1,$2)", monitor.id, bed_a.id)
    with pytest.raises(Exception):  # unique (monitor_id) where active
        await db.execute("insert into bed_assignments(monitor_id, bed_id) values ($1,$2)", monitor.id, bed_b.id)
```

**Implementation Guidance:**
- Confirm users can view and update their personal data (T177/T238).
- Pydantic models in `backend/app/routers/` enforce types, lengths and formats (`EmailStr`, regex for phone, `extra="forbid"`).
- `supabase/migrations/0001_schema.sql` enforces consistency: `not null`, `check` constraints, foreign keys, partial unique index for active monitor-bed assignments, `updated_at` triggers.
- Observations record `author_id` and timestamp server-side (not client-supplied).
- Document data quality checks in `docs/security/data-classification.md`.
- Reference: SD Elements guidance for T743.

**Success Criteria:**
- [ ] Invalid personal data returns 422 for every write endpoint tested.
- [ ] Database constraints reject inconsistent monitor/bed and observation/patient states.
- [ ] Author and timestamp of observations are server-assigned.
- [ ] Tests above pass in CI.

**Status:** Pending
