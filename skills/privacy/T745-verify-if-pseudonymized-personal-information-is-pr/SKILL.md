---
name: t745-verify-if-pseudonymized-personal-information-is-pr
description: Test recipe verifying that ACME Clinical pseudonymized patient identifiers (used in readings, alarms, realtime channels and reports) cannot be re-linked to patient identities from the same data store or by non-authorized roles.
---

# T745: Verify if pseudonymized personal information is protected

**Category:** CODE_FIX
**SD Elements:** [T745](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T745/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
Readings, alarms and realtime monitoring will probably reference patients by name or by the same ID stored next to the name in `patients`, all in the `public` schema readable by any authenticated user. Anyone subscribed to Realtime or reading `readings` can join back to the identity, so the "pseudonym" gives no protection.

**Secure Implementation Pattern:**
```sql
-- supabase/tests/pseudonymization_test.sql (pgTAP)
begin;
select plan(3);

-- identities live in a separate, locked-down schema
select ok(not has_table_privilege('authenticated', 'identity.patient_identity', 'select'),
          'authenticated role cannot read the identity mapping table');

-- operational tables carry only the pseudonym
select hasnt_column('public', 'readings', 'patient_name', 'readings has no direct identifier');

-- biomedical technician cannot re-identify via any view
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-0000000000b1","app_role":"biomed"}';
select is((select count(*) from public.patient_directory)::int, 0,
          'biomed technician sees no name-to-pseudonym mapping');
select * from finish();
rollback;
```

**Implementation Guidance:**
- Verify the design: `public.patients` / `readings` / `alarm_events` / Realtime payloads use `patient_ref` (random, e.g. `PT-` + `secrets.token_hex`) while names, DOB and MRN live in `identity.patient_identity` (separate schema, no `anon`/`authenticated` grants; access only through a security-definer function checking clinical role).
- Test that Realtime channel payloads (`backend/app/services/simulation.py` broadcasting) contain only `patient_ref` and vitals.
- Test that report exports in `backend/app/services/reports.py` contain no identity columns unless the requester is an authorized clinician.
- Run pgTAP via `supabase test db`, plus a pytest asserting a biomed-role token cannot fetch patient names from the API.
- Test fails if any table/view accessible to the operational role holds both pseudonym and identity.
- Reference: SD Elements guidance for T745.

**Success Criteria:**
- [ ] pgTAP test passes: identity schema not readable by `anon`/`authenticated`.
- [ ] No operational table or Realtime payload contains names or MRNs.
- [ ] Biomedical technician/admin roles cannot join pseudonyms to identities via API.
- [ ] Pseudonyms are random, not derived from names, MRN or DOB.

**Status:** Applied
