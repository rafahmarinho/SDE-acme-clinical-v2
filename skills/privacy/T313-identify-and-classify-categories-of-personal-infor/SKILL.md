---
name: t313-identify-and-classify-categories-of-personal-infor
description: Create ACME Clinical's data classification (docs/security/data-classification.md) and machine-readable column labels, identifying staff PII, patient individually identifiable health information, secrets and non-sensitive device data.
---

# T313: Identify and classify categories of personal information

**Category:** CODE_FIX
**SD Elements:** [T313](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T313/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "conseguir para simular as ações). Use pacientes fictícios e monitores simulados para mostrar"
> (EN: manage it to simulate the actions). Use fictitious patients and simulated monitors to show)
> Source: specs/PRD.md, line 29

**What the spec implies (naive approach):**
Because demo patients are fictitious, a developer may treat all data as non-sensitive and skip classification. The same schema would hold real health data in production (vitals, ECG, observations), so access control, retention, logging and anonymization decisions would have no basis.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql (classification labels on columns)
comment on column identity.patient_identity.full_name is 'class=PHI;pii=direct';
comment on column identity.patient_identity.date_of_birth is 'class=PHI;pii=quasi';
comment on column identity.patient_identity.mrn is 'class=PHI;pii=direct';
comment on column public.readings.heart_rate is 'class=PHI;pii=linked-via-pseudonym';
comment on column public.observations.text is 'class=PHI;free-text-may-contain-pii';
comment on column public.profiles.full_name is 'class=PII;pii=direct';
comment on column public.profiles.email is 'class=PII;pii=direct';
comment on column public.profiles.role is 'class=internal';
comment on column public.monitors.serial_number is 'class=internal';
comment on column public.monitors.battery_level is 'class=public-operational';
```

**Implementation Guidance:**
- Write `docs/security/data-classification.md` with a table: data element, location (table/column, Storage bucket, Realtime channel, logs), class (Public, Internal, Confidential, PII, Sensitive PII/PHI), source, purpose, retention, allowed roles.
- Classes: staff name/email/phone = PII; patient name/DOB/MRN, vitals, ECG, observations, alarms = Individually Identifiable Health Information (sensitive); Supabase keys/JWT secret = Secret; monitor metadata = Internal.
- Note compliance drivers (e.g. HIPAA/GDPR/LGPD for real deployments) and that demo data must stay fictitious.
- Mirror labels as `comment on column` in migrations so the classification is testable (T314).
- Use the classification to drive RLS (roles from line 39), log redaction in `backend/app/core/logging.py`, retention (T607) and anonymization (T545).
- Reference: SD Elements guidance for T313.

**Success Criteria:**
- [ ] `docs/security/data-classification.md` exists and covers every table, bucket and channel.
- [ ] Every column in personal-data tables has a `class=` comment.
- [ ] Classification policy is linked from README.
- [ ] T314 verification test passes.

**Status:** Pending
