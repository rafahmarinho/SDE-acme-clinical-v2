---
name: t142-test-that-the-application-s-navigation-flow-is-pro
description: Tests that ACME Clinical rejects out-of-order, skipped, replayed or unrealistically fast steps in multi-step flows (simulation select/advance/reset, monitor-to-bed binding, password recovery) when the API is called directly.
---

# T142: Test that the application's navigation flow is protected

**Category:** CODE_FIX
**SD Elements:** [T142](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T142/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Flows such as binding a monitor to a bed and running simulation scenarios have a natural order enforced by UI screens. Without tests that bypass the UI, server-side sequencing gaps go unnoticed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_navigation_flow.py
import pytest

@pytest.mark.anyio
async def test_advance_without_scenario_rejected(client, admin_headers, fresh_run):
    r = await client.post(f"/api/simulation/{fresh_run}/advance", json={"expected_step": 0}, headers=admin_headers)
    assert r.status_code == 409

@pytest.mark.anyio
async def test_replayed_step_rejected(client, admin_headers, fresh_run):
    await client.post(f"/api/simulation/{fresh_run}/select", json={"scenario": "low_spo2"}, headers=admin_headers)
    ok = await client.post(f"/api/simulation/{fresh_run}/advance", json={"expected_step": 0}, headers=admin_headers)
    replay = await client.post(f"/api/simulation/{fresh_run}/advance", json={"expected_step": 0}, headers=admin_headers)
    assert ok.status_code == 200 and replay.status_code == 409

@pytest.mark.anyio
async def test_bind_to_occupied_bed_rejected(client, nurse_headers):
    await client.post("/api/monitors/demo-mon-1/bind", json={"bed_id": "A1-01", "expected_version": 1}, headers=nurse_headers)
    r = await client.post("/api/monitors/demo-mon-2/bind", json={"bed_id": "A1-01", "expected_version": 1}, headers=nurse_headers)
    assert r.status_code == 409
```

**Implementation Guidance:**
- Add the pytest suite above under `backend/tests/` with fixtures for a fresh simulation run and role-specific tokens; it verifies the control from T67.
- Manual: in the SPA, deep-link directly to later steps (e.g. type the URL of the bind confirmation or simulation run screen) and confirm the UI redirects and the API refuses actions with 409.
- Password recovery: open the reset-password route without a recovery link/session and confirm `updateUser` is not offered and Supabase rejects it; reuse an already-used recovery link and confirm it fails.
- Optional for critical actions: script rapid-fire calls (e.g. 20 advances in 1 s) and confirm they are throttled or rejected.
- Reference: SD Elements guidance for T142.

**Success Criteria:**
- [ ] `backend/tests/test_navigation_flow.py` passes.
- [ ] Manual deep-link and reused recovery link checks fail safely.

**Status:** Pending
