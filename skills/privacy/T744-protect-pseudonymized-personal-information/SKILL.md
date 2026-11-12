---
name: t744-protect-pseudonymized-personal-information
description: Protect the link between ACME Clinical pseudonyms (patient PT-nnnn codes, pseudonymised staff profiles) and real identities by storing identifying fields separately, restricting their access to privileged roles, and exposing only pseudonyms to reporting and secondary consumers.
---

# T744: Protect pseudonymized personal information

**Category:** CODE_FIX
**SD Elements:** [T744](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T744/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "conseguir para simular as ações). Use pacientes fictícios e monitores simulados para mostrar"
> (EN: you can, to simulate the actions). Use fictitious patients and simulated monitors to show)
> Source: specs/PRD.md, line 29

**What the spec implies (naive approach):**
Even with fictitious patients, the app models real PHI handling. A naive schema puts `pseudonym` and `display_name` side by side and grants every role and every view `select *`, so the pseudonym gives no protection: anyone who sees a report row can re-identify the patient.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0009_pseudonym_vault.sql: identifying fields live apart from clinical data
create schema if not exists identity_vault;
revoke all on schema identity_vault from public, anon, authenticated;
create table identity_vault.patient_identity (
  patient_id uuid primary key references public.patients(id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 120),
  birth_year smallint
);
alter table identity_vault.patient_identity enable row level security;
alter table identity_vault.patient_identity force row level security;
create policy identity_need_to_know on identity_vault.patient_identity for select to acme_api_rw
  using (public.has_patient_access(patient_id));       -- assigned ward / break-glass only
grant usage on schema identity_vault to acme_api_rw;
grant select on identity_vault.patient_identity to acme_api_rw;
-- reporting role: no grant at all; reporting.* views expose ward/day aggregates only
```

**Implementation Guidance:**
- Fields to replace with artificial identifiers (agree with the DPO, record in `docs/security/data-classification.md`): patient name, birth year and bed; staff name and e-mail after erasure (`public.pseudonymise_staff` in `supabase/migrations/0007_privacy.sql`).
- Move identifying patient fields out of `public.patients` into a separate, RLS-protected `identity_vault` schema (migration `0009`); clinical tables keep only `patient_id` and `pseudonym`.
- Only the API join in `backend/app/routers/patients.py` resolves names, and only for staff with ward access or an active break-glass grant (`backend/app/routers/break_glass.py`); reports, exports and events (`backend/app/services/reports.py`, `backend/app/routers/events.py`) use pseudonyms only.
- The reporting role and `reporting.*` views (`0007_privacy.sql`) never get vault access; the browser (`anon`/`authenticated`) never gets it either.
- Pseudonyms must not be derived from identity (no hash of the name); generate them randomly and keep the mapping only in the vault.
- Log every vault read for an unassigned ward through `backend/app/core/audit.py`.
- Reference: SD Elements guidance for T744.

**Success Criteria:**
- [ ] `backend/tests/test_privacy.py::test_t745_reporting_role_cannot_read_patient_linked_rows` and `test_t745_browser_and_device_roles_cannot_re_identify` pass, extended to the `identity_vault` schema.
- [ ] Pytest: a nurse not assigned to the ward gets the pseudonym but not the display name; with break-glass the name is returned and the access is audited.
- [ ] Pytest: CSV export and audit report contain `PT-nnnn` codes and no `display_name` values.

**Status:** Pending
