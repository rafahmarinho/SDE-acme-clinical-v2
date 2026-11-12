---
name: t2273-verify-that-unified-and-manageable-interfaces-are
description: Test recipe verifying ACME Clinical's administrator Security Settings screen/API enforces a secure baseline, restricts access to administrators, audits changes and lets admins detect and approve configuration integrity.
---

# T2273: Verify that unified and manageable interfaces are available for security settings and configuration parameters

**Category:** CODE_FIX
**SD Elements:** [T2273](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2273/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "perda de conexão. Tenha perfis de enfermeiro, médico, técnico biomédico e administrador."
> (EN: connection loss. Have nurse, physician, biomedical technician and administrator profiles.)
> Source: specs/PRD.md, line 39

**What the spec implies (naive approach):**
With four roles, settings pages are frequently hidden in the UI for non-admins but still writable via the API. Baseline enforcement and integrity checks are not tested, so a weakened setting can go unnoticed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_security_settings.py
import pytest

@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["nurse", "physician", "biomed"])
async def test_non_admin_cannot_change_settings(client, token_for, role):
    r = await client.put("/admin/security-settings", headers=auth(token_for(role)),
                         json={"session_idle_minutes": 60})
    assert r.status_code == 403

@pytest.mark.asyncio
async def test_baseline_enforced(client, admin_token):
    r = await client.put("/admin/security-settings", headers=auth(admin_token),
                         json={"session_idle_minutes": 600, "password_min_length": 4})
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_integrity_drift_detected(client, admin_token, db):
    await client.post("/admin/security-settings/approve", headers=auth(admin_token))
    await db.execute("update security_settings set allow_simulation_reset = true")  # out-of-band change
    rep = (await client.get("/admin/security-settings/report", headers=auth(admin_token))).json()
    assert rep["fingerprint"] != rep["approved_fingerprint"]
```

**Implementation Guidance:**
- Test the T371 implementation (`backend/app/routers/settings.py`, settings screen in `frontend/src/screens/`).
- Verify the baseline in `docs/security/configuration.md` matches the Pydantic bounds.
- Frontend vitest: settings route not rendered in navigation for non-admin roles.
- Verify an `audit_events` row is created per change.
- Reference: SD Elements guidance for T2273.

**Success Criteria:**
- [ ] Non-admin roles receive 403 for read and write of security settings.
- [ ] Out-of-baseline values rejected with 422.
- [ ] Out-of-band changes are detected by the integrity report.
- [ ] Every change produces an audit event.

**Status:** Applied
