---
name: t314-verify-that-personal-and-confidential-information
description: Test recipe verifying every ACME Clinical table column, Storage bucket and Realtime payload is classified (PII, PHI, confidential, internal) and that the classification matches the documented policy.
---

# T314: Verify that personal and confidential information is identified and classified

**Category:** CODE_FIX
**SD Elements:** [T314](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T314/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: complete, database configuration, initial data, environment variable examples and a)
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
The database configuration and seed are delivered without any classification check, so new columns (e.g. a patient phone or free-text note) get added without anyone deciding how they must be protected.

**Secure Implementation Pattern:**
```sql
-- supabase/tests/classification_test.sql (pgTAP)
begin;
select plan(1);
select is_empty($$
  select c.table_schema || '.' || c.table_name || '.' || c.column_name
  from information_schema.columns c
  join pg_class t on t.relname = c.table_name
  join pg_namespace n on n.oid = t.relnamespace and n.nspname = c.table_schema
  where c.table_schema in ('public', 'identity')
    and coalesce(col_description(t.oid, c.ordinal_position), '') not like 'class=%'
$$, 'every column in public/identity schemas carries a class= label');
select * from finish();
rollback;
```

**Implementation Guidance:**
- Run the pgTAP test with `supabase test db` in CI; it fails when a column is unlabeled.
- Add a pytest (`backend/tests/test_classification_doc.py`) that parses `docs/security/data-classification.md` and checks each `class=PHI|PII` column appears in the document and vice versa.
- Manually review Storage buckets and Realtime channel payloads against the document.
- Verify PHI columns are only in tables protected by RLS for clinical roles.
- Reference: SD Elements guidance for T314.

**Success Criteria:**
- [ ] pgTAP classification test passes on the full schema.
- [ ] Document and schema labels are consistent (pytest).
- [ ] Each PHI/PII table has RLS enabled (checked in the same pgTAP suite).
- [ ] Storage buckets and Realtime channels are listed in the classification document.

**Status:** Applied
