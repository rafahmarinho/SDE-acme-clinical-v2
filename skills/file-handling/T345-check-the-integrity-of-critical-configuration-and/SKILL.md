---
name: t345-check-the-integrity-of-critical-configuration-and
description: Protects the integrity of ACME Clinical's critical data such as alarm threshold settings, simulation scenario definitions and stored clinical files by hashing them, verifying the hash on every use and alerting administrators and failing safe on mismatch.
---

# T345: Check the integrity of critical configuration and data files

**Category:** CODE_FIX
**SD Elements:** [T345](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T345/)
**Priority:** 4/10 · **Phase:** development

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: threshold settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

> "Prepare dados de demonstração com doze pacientes e dez monitores. Inclua uma área para"
> (EN: Prepare demo data with twelve patients and ten monitors. Include an area to)
> Source: specs/PRD.md, line 41

**What the spec implies (naive approach):**
Alarm thresholds and scenario definitions read from a DB row or JSON file and trusted blindly. A silent modification (e.g. SpO2 low limit set to 50 via direct DB/Storage access) would suppress life-critical alarms without anyone noticing.

**Secure Implementation Pattern:**
```python
# backend/app/services/alarms.py
import hashlib, hmac, json
from app.core.config import settings

SAFE_DEFAULTS = {"spo2_low": 90, "hr_low": 40, "hr_high": 140, "rr_low": 8, "rr_high": 30}

def config_mac(cfg: dict, updated_at: str) -> str:
    payload = json.dumps({"cfg": cfg, "updated_at": updated_at}, sort_keys=True).encode()
    return hmac.new(settings.config_integrity_key.encode(), payload, hashlib.sha256).hexdigest()

async def load_thresholds(db, patient_id) -> dict:
    row = await db.get_thresholds(patient_id)       # cfg, updated_at, mac
    if row and hmac.compare_digest(row.mac, config_mac(row.cfg, row.updated_at)):
        return row.cfg
    sec_event("config_integrity_violation", outcome="fail", user_id=None, ip=None,
              patient_id=str(patient_id))
    await notify_admins("threshold_integrity_violation")
    return SAFE_DEFAULTS                            # fail safe: keep alarms active
```

**Implementation Guidance:**
- Identify critical data: per-patient alarm thresholds, simulation scenario definitions (`services/simulation.py`), role assignments, and uploaded clinical files in Storage (store `sha256` at upload per T2167 and verify on report embedding).
- Compute HMAC-SHA256 (keyed, so it acts as a signature) over content + last-modified timestamp when the backend writes the record; key lives only in backend Vercel env (`CONFIG_INTEGRITY_KEY`).
- Verify on every use (alarm evaluation, scenario load, file use in reports). On mismatch: log a security event, alert administrators (Realtime/system_alerts), and fail safe (default clinical thresholds; refuse to run a tampered scenario).
- Bundled config files (`vercel.json`, Python settings) are immutable in the Vercel deployment; no runtime-writable config files exist — note this explicitly.
- Reference: SD Elements guidance for T345.

**Success Criteria:**
- [ ] Threshold and scenario rows carry a MAC written only by the backend.
- [ ] Tampered rows trigger a security event, admin alert and safe defaults (unit test).
- [ ] Stored file `sha256` is verified before use.

**Status:** Applied
