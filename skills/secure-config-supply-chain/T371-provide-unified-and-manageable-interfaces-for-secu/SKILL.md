---
name: t371-provide-unified-and-manageable-interfaces-for-secu
description: Build a single administrator-only Security Settings screen and API in ACME Clinical for session timeout, password policy, retention, simulation reset and alarm-limit change permissions, with a configuration report and integrity check of the active settings.
---

# T371: Provide unified and manageable interfaces for security settings and configuration parameters

**Category:** CODE_FIX
**SD Elements:** [T371](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T371/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
"Configurações" and "configurações de limites" will likely be scattered: some values in env vars, some hard-coded, alarm thresholds in one screen, retention nowhere. Administrators cannot see the effective security configuration or detect tampering, and any role can change settings via the API.

**Secure Implementation Pattern:**
```python
# backend/app/routers/settings.py
import hashlib, json
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.core.security import require_role
from app.core.config import settings as env

router = APIRouter(prefix="/admin/security-settings", dependencies=[Depends(require_role("admin"))])

class SecuritySettings(BaseModel):
    session_idle_minutes: int = Field(15, ge=5, le=60)
    password_min_length: int = Field(12, ge=12, le=128)
    retention_days_observations: int = Field(365, ge=30)
    allow_simulation_reset: bool = False
    threshold_editors: list[str] = ["physician", "admin"]

def fingerprint(s: SecuritySettings) -> str:
    return hashlib.sha256(json.dumps(s.model_dump(), sort_keys=True).encode()).hexdigest()

@router.get("/report")
async def report():
    s = await load_settings()
    return {"settings": s, "fingerprint": fingerprint(s),
            "approved_fingerprint": await approved_fingerprint(),
            "env": {"app_env": env.app_env, "docs_enabled": env.enable_docs},
            "components": await component_versions()}

@router.put("")
async def update(body: SecuritySettings, user=Depends(require_role("admin"))):
    await save_settings(body, changed_by=user.id)       # writes audit_events row
    return {"fingerprint": fingerprint(body)}
```

**Implementation Guidance:**
- Store DB-managed security settings in a single `security_settings` table (`supabase/migrations/0001_schema.sql`) with RLS: admin-only update, audit trigger to `audit_events`.
- Expose `GET/PUT /admin/security-settings` and `GET /report` in `backend/app/routers/settings.py`; validate bounds with Pydantic so settings cannot go below a secure baseline.
- Build one "Security settings" screen under settings in `frontend/src/screens/`, visible only in the administrator navigation (PRD: navigation adapted to profiles); show env-controlled values read-only.
- Provide a downloadable configuration report (settings, environment flags, component versions) and an "Approve configuration" action storing the fingerprint; show a warning when the live fingerprint differs from the approved one.
- Reference: SD Elements guidance for T371.

**Success Criteria:**
- [ ] All security parameters are viewable/editable from one admin screen.
- [ ] Non-admin roles get 403 on the settings API and do not see the screen.
- [ ] Changes are audited; values outside the baseline return 422.
- [ ] Report shows a fingerprint mismatch after an unapproved change.

**Status:** Pending
