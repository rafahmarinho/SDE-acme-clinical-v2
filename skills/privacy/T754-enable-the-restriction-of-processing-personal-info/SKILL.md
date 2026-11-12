---
name: t754-enable-the-restriction-of-processing-personal-info
description: Let ACME Clinical record per-person restrictions on specific processing activities (e.g. a staff member objecting to inclusion in activity reports, or a patient record under restriction excluded from research views) and check them before every such activity.
---

# T754: Enable the restriction of processing personal information of an individual for a specific purpose

**Category:** CODE_FIX
**SD Elements:** [T754](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T754/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Reports and team management process staff and patient data for several purposes (care, staff activity reports, audit summaries, aggregate statistics). A naive design has no notion of an objection: every report query includes everyone, so a restriction requested by a data subject cannot be honored without deleting data.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0009_processing_restrictions.sql
create type public.processing_activity as enum ('staff_activity_report', 'aggregate_statistics', 'login_analytics');
create table public.processing_restrictions (
  subject_type text not null check (subject_type in ('staff', 'patient')),
  subject_id uuid not null,
  activity public.processing_activity not null,
  reason text not null check (char_length(reason) between 3 and 500),
  restricted_at timestamptz not null default now(), restricted_by uuid not null,
  lifted_at timestamptz,
  primary key (subject_type, subject_id, activity, restricted_at)
);
create or replace function public.processing_allowed(p_type text, p_id uuid, p_activity public.processing_activity)
returns boolean language sql stable as $$
  select not exists (select 1 from public.processing_restrictions
                     where subject_type = p_type and subject_id = p_id and activity = p_activity and lifted_at is null)
$$;
```
```python
# backend/app/services/reports.py - filter restricted subjects inside the query
rows = await fetch_all(conn, """select ... from public.events e
    where e.at between %s and %s
      and public.processing_allowed('staff', e.actor_id, 'staff_activity_report')""", (start, end))
```

**Implementation Guidance:**
- From the PIA / processing register (`docs/security/privacy.md`, `docs/security/data-classification.md`) list the activities a person can object to; clinical care and legally required audit logging are not restrictable, but secondary uses (staff activity reports, statistics, analytics) are.
- Add `public.processing_restrictions` and `processing_allowed()` (migration `0009`), with RLS: only administrators (`staff:manage`) create or lift restrictions; staff can read their own.
- Add admin endpoints in `backend/app/routers/staff.py` (patients: `backend/app/routers/patients.py`) to set/lift a restriction, audited via `backend/app/core/audit.py`; staff can request one from `frontend/src/screens/Profile.tsx`.
- Check before processing: report builders in `backend/app/services/reports.py` and the `reporting.*` views in `0007_privacy.sql` exclude restricted subjects; exports and any future analytics call `processing_allowed()`.
- Restricted data stays stored but is not processed; if an activity cannot be halted immediately, exclude the subject at the query layer as above.
- Reference: SD Elements guidance for T754.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_privacy.py`): after restricting `staff_activity_report` for user X, `GET /v1/reports/audit` and the CSV export omit X; lifting the restriction includes X again.
- [ ] Pytest: only administrators can create/lift restrictions (403 for nurse, physician, biomedical technician), and both actions are audited.
- [ ] Pytest: clinical endpoints (patient detail, alarms) are unaffected by restrictions on secondary activities.

**Status:** Pending
