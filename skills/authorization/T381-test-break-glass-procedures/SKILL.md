---
name: t381-test-break-glass-procedures
description: Test the ACME Clinical break-glass emergency access flow end to end, checking the warning and acknowledgement, complete audit logging, minimal scope and that grants expire or are revoked so normal ward-scoped operation is restored.
---

# T381: Test break-glass procedures

**Category:** CODE_FIX
**SD Elements:** [T381](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T381/)
**Priority:** 3/10 · **Phase:** testing

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: "ward view, patient list and detail, live monitoring, alarms, devices,")
> Source: specs/PRD.md, line 25

**What the spec implies (naive approach):**
An emergency path that is rarely used is rarely tested: grants may never expire, the warning may be skippable via the API, or audit entries may lack the reason or the actions performed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_break_glass.py
async def test_full_break_glass_cycle(client_as, nurse_ward_a, ward_b_patient, freezer, audit_rows):
    c = client_as(nurse_ward_a, auth_age_minutes=0)
    assert (await c.get(f"/api/patients/{ward_b_patient.id}")).status_code == 404

    # warning acknowledgement is mandatory server-side
    bad = await c.post("/api/break-glass", json={"patient_id": str(ward_b_patient.id), "reason": "Code blue bed 4"})
    assert bad.status_code == 422

    g = (await c.post("/api/break-glass", json={"patient_id": str(ward_b_patient.id),
          "reason": "Code blue bed 4, covering nurse", "acknowledged_warning": True})).json()
    assert (await c.get(f"/api/patients/{ward_b_patient.id}")).status_code == 200
    assert (await c.put(f"/api/thresholds/{ward_b_patient.threshold_id}", json={})).status_code == 403

    freezer.tick(timedelta(minutes=31))
    assert (await c.get(f"/api/patients/{ward_b_patient.id}")).status_code == 404   # restored

    events = [e for e in audit_rows() if e["grant_id"] == g["id"]]
    assert {"break_glass.activated", "patient.read", "break_glass.expired"} <= {e["action"] for e in events}
    assert all(e["actor_id"] == str(nurse_ward_a.id) for e in events)
```

**Implementation Guidance:**
- Automate the cycle above in `backend/tests/test_break_glass.py`; add a frontend test that `BreakGlassDialog` cannot submit until the warning is accepted and a reason entered.
- Verify audit completeness: who, which patient, reason, start, every action, expiry/revocation, source IP.
- Verify early revocation by the user or an administrator ends access immediately and closes Realtime subscriptions.
- With designers, walk through emergency scenarios (desaturation alarm in another ward, monitor connection loss while the assigned nurse is unavailable) to ensure no needed emergency function is missing from `BREAK_GLASS_PERMS`.
- Reference: SD Elements guidance for T381.

**Success Criteria:**
- [ ] Automated cycle test passes, including expiry and scope limits.
- [ ] Audit log contains every required field for the grant.
- [ ] Documented review confirms all emergency functions are covered.

**Status:** Pending
