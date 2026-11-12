---
name: t128-test-for-access-control-bypass-through-user-contro
description: Test ACME Clinical for IDOR by swapping patient, ward, alarm, monitor, observation and staff identifiers in API paths, query strings and bodies, confirming users cannot reach records outside their ward or role.
---

# T128: Test for access control bypass through user-controlled keys

**Category:** CODE_FIX
**SD Elements:** [T128](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T128/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow binding a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: "ward view, patient list and detail, live monitoring, alarms, devices,")
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
Endpoints like `GET /patients/{id}`, `POST /alarms/{id}/ack` or `POST /observations {patient_id}` would fetch by the supplied ID only. Changing the ID would expose or modify another ward's patient, or let a user record observations under someone else's `author_id`.

**Secure Implementation Pattern:**
```python
# backend/tests/test_idor.py
import pytest

@pytest.mark.parametrize("method,path", [
    ("GET",  "/api/patients/{other_patient}"),
    ("GET",  "/api/patients/{other_patient}/vitals"),
    ("POST", "/api/alarms/{other_alarm}/ack"),
    ("GET",  "/api/reports/{other_report}/download"),
])
async def test_cross_ward_ids_rejected(client_as, nurse_ward_a, ward_b_ids, method, path):
    r = await client_as(nurse_ward_a).request(method, path.format(**ward_b_ids))
    assert r.status_code == 404          # same as nonexistent; no data leak

async def test_body_keys_cannot_impersonate(client_as, nurse_ward_a, ward_a_patient, physician):
    r = await client_as(nurse_ward_a).post("/api/observations", json={
        "patient_id": str(ward_a_patient.id), "note": "ok",
        "author_id": str(physician.id)})         # mass-assignment attempt
    assert r.status_code in (201, 422)
    if r.status_code == 201:
        assert r.json()["author_id"] == str(nurse_ward_a.id)

async def test_list_filter_tampering(client_as, nurse_ward_a, ward_b_ids):
    r = await client_as(nurse_ward_a).get(f"/api/patients?ward_id={ward_b_ids['ward']}")
    assert r.json()["items"] == []
```

**Implementation Guidance:**
- Inventory every endpoint taking an object key in `backend/app/routers/*.py` (patients, wards, beds, monitors, alarms, observations, reports, files, staff, maintenance tickets).
- Use UUIDs (not sequential IDs) in `supabase/migrations/0001_schema.sql`, but do not rely on them: the test must use known valid IDs from another ward.
- Pydantic input models (`extra="forbid"`) must not accept `author_id`, `ward_id` of the actor, `role` or `acknowledged_by`; the server derives them from `CurrentUser`.
- Expect 404 for objects outside scope to avoid confirming existence.
- Reference: SD Elements guidance for T128.

**Success Criteria:**
- [ ] All key-swap tests in `backend/tests/test_idor.py` pass for each role.
- [ ] Mass-assignment attempts yield 422 or are ignored, never stored.
- [ ] Manual proxy session confirms the same on a Vercel preview.

**Status:** Applied
