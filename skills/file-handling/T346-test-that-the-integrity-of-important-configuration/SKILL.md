---
name: t346-test-that-the-integrity-of-important-configuration
description: Tests that ACME Clinical detects tampering of alarm thresholds, simulation scenarios and stored clinical files, reports an integrity error and fails safe instead of silently using altered data.
---

# T346: Test that the integrity of important configuration and data files are checked

**Category:** CODE_FIX
**SD Elements:** [T346](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T346/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: threshold settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Threshold settings are tested only through the UI. Direct modification of the DB row or Storage object is never attempted, so missing integrity checks go unnoticed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_integrity_checks.py
import pytest
from app.services import alarms, simulation

@pytest.mark.asyncio
async def test_tampered_threshold_detected(db, patient_id, caplog, admin_alerts):
    await db.execute("update thresholds set cfg = jsonb_set(cfg, '{spo2_low}', '50') "
                     "where patient_id = $1", patient_id)          # bypasses backend MAC
    cfg = await alarms.load_thresholds(db, patient_id)
    assert cfg["spo2_low"] == alarms.SAFE_DEFAULTS["spo2_low"]
    assert "config_integrity_violation" in caplog.text
    assert "threshold_integrity_violation" in admin_alerts()

@pytest.mark.asyncio
async def test_tampered_scenario_refused(db, scenario_id):
    await db.execute("update scenarios set steps = '[]' where id = $1", scenario_id)
    with pytest.raises(simulation.IntegrityError):
        await simulation.load_scenario(db, scenario_id)

@pytest.mark.asyncio
async def test_tampered_file_detected(storage, file_row):
    storage.overwrite(file_row.object_key, b"%PDF-1.4 altered")
    with pytest.raises(simulation.IntegrityError):
        await simulation.load_attachment(file_row.id)
```

**Implementation Guidance:**
- With developers, list protected items (from T345): thresholds, scenario definitions, role assignments, stored file hashes.
- For each, modify the data out-of-band (SQL as service role on the local Supabase stack, Storage overwrite) and call the function that uses it.
- The test fails if processing continues with altered data and no error/alert is produced.
- Also verify that legitimate updates via the API recompute the MAC and still pass.
- Reference: SD Elements guidance for T346.

**Success Criteria:**
- [ ] `backend/tests/test_integrity_checks.py` passes for every protected item.
- [ ] Each tamper produces a security event and admin alert.
- [ ] Legitimate API updates are not flagged.

**Status:** Applied
