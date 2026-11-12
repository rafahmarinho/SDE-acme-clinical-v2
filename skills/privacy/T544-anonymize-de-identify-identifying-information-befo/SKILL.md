---
name: t544-anonymize-de-identify-identifying-information-befo
description: Anonymize ACME Clinical patient and staff data before any secondary use (aggregate reports, statistics, exports, demo datasets) by removing direct identifiers, generalising quasi-identifiers and suppressing small cells, through dedicated de-identified views.
---

# T544: Anonymize (de-identify) identifying information before using it for a secondary purpose

**Category:** CODE_FIX
**SD Elements:** [T544](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T544/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
"Reports" are often built by exporting raw rows - patient name, birth year, bed, alarms with timestamps - into a CSV for management or quality review. That is a secondary purpose; with small wards a single row or a count of 1 identifies a person.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0007_privacy.sql - reporting schema exposes aggregates only
create or replace view reporting.ward_alarm_daily as
select w.code as ward_code, (date_trunc('day', a.raised_at))::date as day, a.type::text as alarm_type,
       a.priority::text as priority, count(*)::int as alarm_count       -- no patient columns
  from public.alarms a
  join public.patients p on p.id = a.patient_id
  join public.wards w on w.id = p.ward_id
 group by w.code, (date_trunc('day', a.raised_at))::date, a.type, a.priority
having count(*) >= 5;                                                   -- small-cell suppression (k >= 5)
```
```python
# backend/app/services/privacy.py
MIN_CELL_SIZE = 5
def suppress_small_counts(counts: Mapping[str, int], k: int = MIN_CELL_SIZE) -> dict[str, int | None]:
    return {key: (value if value >= k else None) for key, value in counts.items()}

# backend/app/services/reports.py - secondary-use builders read reporting.* only, never public.patients
rows = await fetch_all(conn, """select ward_code, day, alarm_type, priority, alarm_count
                                from reporting.ward_alarm_daily where day between %s and %s""", (start, end))
```

**Implementation Guidance:**
- Define secondary purposes in `docs/security/privacy.md` (quality reports, statistics, training/demo datasets) versus the primary purpose (care on the live screens).
- Secondary-use code paths (`backend/app/services/reports.py`, `GET /v1/reports/ward-activity`, `/v1/reports/export.csv`) read only `reporting.*` views or apply `suppress_small_counts`; they never select names, pseudonyms, birth years, bed IDs or exact timestamps.
- Generalise quasi-identifiers: day instead of timestamp, ward instead of bed, age bands instead of birth year; drop free-text observations entirely.
- The reporting role loses raw-table access (`0007_privacy.sql`); new secondary views require a privacy review and a test.
- If de-identification is delegated to a processor, provide written instructions (record in `docs/security/privacy.md`).
- Seed/demo data (`supabase/seed.sql`) stays fictional; never copy real data into demo or test environments.
- Reference: SD Elements guidance for T544.

**Success Criteria:**
- [ ] `backend/tests/test_privacy.py::test_t545_reporting_views_are_aggregated_and_suppress_small_cells` and `test_t545_statistics_helpers_and_ward_report_hold_no_identifiers` pass.
- [ ] Pytest: a ward/day with 3 alarms of a type is absent from `reporting.ward_alarm_daily` (or `null` via `suppress_small_counts`), never reported as 3.
- [ ] Pytest: the CSV export contains no column named like `name`, `pseudonym`, `birth`, `bed` or `email`.

**Status:** Applied
