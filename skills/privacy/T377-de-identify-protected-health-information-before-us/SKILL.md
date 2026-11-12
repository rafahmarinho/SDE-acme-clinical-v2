---
name: t377-de-identify-protected-health-information-before-us
description: De-identify ACME Clinical protected health information (vital signs, ECG traces, alarms, observations, attachments linked to a patient) using HIPAA Safe Harbor-style removal of identifiers before it is used for any purpose other than the patient's care.
---

# T377: De-identify protected health information before using it for a secondary purpose

**Category:** CODE_FIX
**SD Elements:** [T377](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T377/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "conseguir para simular as ações). Use pacientes fictícios e monitores simulados para mostrar"
> "frequência cardíaca, saturação, respiração, pressão arterial e um traçado sintético de ECG."
> (EN: you can, to simulate the actions). Use fictitious patients and simulated monitors to show heart rate, saturation, respiration, blood pressure and a synthetic ECG trace.)
> Source: specs/PRD.md, lines 29-31

**What the spec implies (naive approach):**
Readings and ECG traces are attractive for research, algorithm tuning or alarm-threshold studies. A naive export dumps `readings` joined to `patients` with patient IDs, bed numbers and exact timestamps; date plus ward plus a rare event is enough to re-identify a patient.

**Secure Implementation Pattern:**
```python
# backend/app/services/reports.py - de-identified research extract (Safe Harbor style)
PHI_DROP = {"patient_id", "pseudonym", "display_name", "birth_year", "bed_id", "monitor_serial", "observation_text"}

def deidentify_reading(row: Mapping[str, Any], study_key: bytes) -> dict[str, Any]:
    out = {k: v for k, v in row.items() if k not in PHI_DROP}
    out["subject"] = hmac.new(study_key, str(row["patient_id"]).encode(), hashlib.sha256).hexdigest()[:16]
    out["t_offset_min"] = int((row["taken_at"] - row["admitted_at"]).total_seconds() // 60)  # no dates
    out.pop("taken_at", None); out.pop("admitted_at", None)
    out["age_band"] = age_band(row.get("birth_year"))           # 90+ collapsed
    return out
# study_key: random per extract, never stored with the extract -> subjects cannot be linked back
```

**Implementation Guidance:**
- Define primary purpose (care in the live screens) and secondary purposes (research, algorithm/threshold tuning, training datasets) in `docs/security/privacy.md` and the usage agreement.
- Any secondary-use extract goes through a single de-identification function in `backend/app/services/reports.py`: remove the 18 Safe Harbor identifiers that apply (names, dates other than year, device identifiers/serials, record numbers, free text, file attachments), replace patient IDs with a per-extract keyed pseudonym, and shift times to offsets.
- Expose it only via an admin-only, audited endpoint (`backend/app/routers/reports.py`) with `require(Perm.reports_admin)` and small-cell suppression (`suppress_small_counts`, `MIN_CELL_SIZE`) for any aggregate.
- Never include Storage attachments (`clinical-files` bucket) or `observations` free text in extracts.
- If expert determination is used instead of Safe Harbor, record the method and approval in `docs/security/privacy.md`.
- Reference: SD Elements guidance for T377.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_privacy.py`): the de-identified extract has none of the `PHI_DROP` fields, no `datetime` values, and the same patient gets different subject codes in two extracts.
- [ ] Pytest: the extract endpoint is admin-only (403 for other roles) and writes an audit event with row counts only.
- [ ] Pytest: no extract contains Storage object paths or observation text.

**Status:** Applied
