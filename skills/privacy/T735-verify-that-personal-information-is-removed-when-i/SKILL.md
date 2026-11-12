---
name: t735-verify-that-personal-information-is-removed-when-i
description: Test recipe verifying that ACME Clinical removes staff and patient personal/health data (profiles, observations, alarm and event history) when its retention period ends, including backups, Supabase Storage files and third-party copies.
---

# T735: Verify that personal information is removed when it is no longer needed

**Category:** CODE_FIX
**SD Elements:** [T735](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T735/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: choose scenarios, advance the simulation, view events and reset the data. The results)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
The PRD asks for persisted data ("continuar salvos após recarregar") and a "reset data" action, but no retention rules. A naive build keeps every observation, alarm, event and deactivated staff profile forever, and the reset only truncates a few tables while leaving Storage objects, auth users and backups untouched. Without a test, nobody notices personal/health data outliving its purpose.

**Secure Implementation Pattern:**
```python
# backend/tests/test_retention_purge.py
from datetime import datetime, timedelta, timezone
import pytest
from app.services import retention  # implements T607

@pytest.mark.asyncio
async def test_expired_records_are_purged(db, storage, seed_factory):
    old = datetime.now(timezone.utc) - timedelta(days=400)
    obs = await seed_factory.observation(created_at=old, last_activity_at=old)
    staff = await seed_factory.staff(deactivated_at=old)
    held = await seed_factory.observation(created_at=old, legal_hold=True)

    report = await retention.run_purge(db, storage, now=datetime.now(timezone.utc))

    assert await db.fetchval("select count(*) from observations where id=$1", obs.id) == 0
    assert await db.fetchval("select count(*) from profiles where id=$1", staff.id) == 0
    assert await storage.list(prefix=f"observations/{obs.id}/") == []
    assert await db.fetchval("select count(*) from observations where id=$1", held.id) == 1
    # audit evidence: counts only, never personal data
    assert report.deleted["observations"] >= 1
    assert "full_name" not in report.model_dump_json()
```

**Implementation Guidance:**
- Write the test against `backend/app/services/retention.py` (the purge job from T607) and `supabase/migrations/0001_schema.sql` (`retention_policies`, `purge_log` tables).
- Seed records past and before their retention window; assert expired rows, related Storage objects (`supabase.storage`) and Supabase Auth users of removed staff are gone, and restricted/legal-hold rows remain.
- Verify the "reiniciar os dados" reset in `backend/app/routers/simulation.py` deletes demo data across all tables and Storage, not only readings.
- Manual check: document in `docs/security/data-classification.md` the retention schedule per category, the Supabase backup/PITR window (deleted data ages out of backups after N days), and that no third parties hold copies (integrations are simulated).
- Keep `purge_log` entries as evidence (timestamp, category, count) without personal data.
- Reference: SD Elements guidance for T735.

**Success Criteria:**
- [ ] `backend/tests/test_retention_purge.py` passes: expired records and their Storage files are deleted; legal-hold rows are kept.
- [ ] The reset endpoint test asserts zero remaining demo patient/observation rows and Storage objects afterwards.
- [ ] Retention schedule and backup expiry window are documented and linked from README.
- [ ] `purge_log` contains an entry per run with counts only.

**Status:** Applied
