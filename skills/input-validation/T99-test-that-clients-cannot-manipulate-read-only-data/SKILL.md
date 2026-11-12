---
name: t99-test-that-clients-cannot-manipulate-read-only-data
description: Test recipe confirming that ACME Clinical clients cannot alter server-owned data (alarm author/severity, monitor-bed bindings, roles, observation authorship) by tampering with requests.
---

# T99: Test that clients cannot manipulate read-only data

**Category:** CODE_FIX
**SD Elements:** [T99](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T99/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow linking a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Forms for observations, alarm acknowledgement, monitor binding and profile editing may carry hidden fields (user id, role, ward, severity). Without tests nobody notices that a proxy-modified request can change these server-owned values.

**Secure Implementation Pattern:**
```python
# backend/tests/test_readonly_tampering.py
import pytest

@pytest.mark.asyncio
async def test_forged_author_rejected(client, nurse_headers, other_user_id, alarm_id):
    r = await client.post(f"/api/alarms/{alarm_id}/ack",
                          json={"note": "ok", "acknowledged_by": str(other_user_id)},
                          headers=nurse_headers)
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_profile_cannot_escalate_role(client, nurse_headers):
    r = await client.patch("/api/profile", json={"display_name": "N", "role": "administrator"},
                           headers=nurse_headers)
    assert r.status_code == 422
    me = (await client.get("/api/profile", headers=nurse_headers)).json()
    assert me["role"] == "nurse"

@pytest.mark.asyncio
async def test_observation_author_from_token(client, nurse_headers, patient_id, nurse_id):
    r = await client.post(f"/api/patients/{patient_id}/observations",
                          json={"text": "Stable"}, headers=nurse_headers)
    assert r.json()["author_id"] == str(nurse_id)
```

**Implementation Guidance:**
- List inputs that must never be user-modified: hidden fields, cookies, local storage values, role claims, computed alarm fields, server timestamps.
- Verify the client only sends pointers (UUIDs) and the Supabase session token; use an HTTP proxy (Burp/ZAP) on the frontend screens to modify such fields manually as a complement.
- Assert tampered requests are rejected (422) or ignored, and that persisted data reflects server state.
- Also test directly against Supabase PostgREST with the anon key to confirm RLS blocks updates to `role`, `acknowledged_by` and similar columns.
- Reference: SD Elements guidance for T99.

**Success Criteria:**
- [ ] `backend/tests/test_readonly_tampering.py` passes for alarms, observations, profile and monitor binding endpoints.
- [ ] Manual proxy test documented: modified hidden/read-only fields have no effect.
- [ ] Direct Supabase update of a protected column with a user JWT fails due to RLS.

**Status:** Pending
