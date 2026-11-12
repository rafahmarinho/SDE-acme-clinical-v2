---
name: t545-verify-that-personal-information-is-anonymized-bef
description: Test recipe verifying ACME Clinical anonymizes patient and staff data before secondary use such as aggregate reports, analytics, demo exports or the 3D simulation view, with a documented de-identification procedure.
---

# T545: Verify that personal information is anonymized before being reused for secondary purposes

**Category:** CODE_FIX
**SD Elements:** [T545](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T545/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: frontend. Reading generation, alarms and reports must be done in Python. The)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
Reports will most likely be generated straight from the patient and alarm tables, including names, bed numbers and staff names, and reused for ward statistics or exported CSVs. That reuses identifiable health data for a secondary purpose (quality/statistics) without de-identification.

**Secure Implementation Pattern:**
```python
# backend/tests/test_report_anonymization.py
import re, pytest
from app.services.reports import build_ward_statistics

IDENTIFIERS = re.compile(r"(PT-[0-9a-f]+|@|\b\d{4}-\d{2}-\d{2}\b)")

@pytest.mark.asyncio
async def test_statistics_report_is_deidentified(db, seed_demo):
    report = await build_ward_statistics(db, ward="ICU", period_days=30)
    payload = report.model_dump_json()
    for p in seed_demo.patients:
        assert p.full_name not in payload
        assert p.mrn not in payload
    assert not IDENTIFIERS.search(payload)
    # small cells suppressed to limit re-identification (k >= 5)
    assert all(row.count >= 5 or row.count is None for row in report.rows)
    # staff are aggregated by role, never by name
    assert {r.group for r in report.rows} <= {"nurse", "physician", "biomed", "admin", "ward"}
```

**Implementation Guidance:**
- Identify secondary uses: aggregate reports, alarm-performance statistics, exports, 3D simulation visuals, logs/analytics. Primary care views (patient detail for treating staff) are out of scope.
- In `backend/app/services/reports.py`, build statistics from an anonymized projection: drop names/MRN/DOB/pseudonyms, generalize timestamps to day or hour, bucket ages, suppress groups with count < 5.
- Document the de-identification procedure and re-identification risk assessment in `docs/security/data-classification.md`.
- Test fails if any identifier or pseudonym appears in a secondary-use output.
- Reference: SD Elements guidance for T545.

**Success Criteria:**
- [ ] `backend/tests/test_report_anonymization.py` passes for every statistics/export report.
- [ ] Small-count cells are suppressed.
- [ ] De-identification procedure and risk assessment are documented.
- [ ] Patient-identifying reports are restricted to clinical roles and labeled as primary use.

**Status:** Pending
