---
name: t426-verify-that-the-authenticity-of-external-devices-a
description: Tests that ACME Clinical only accepts vitals from, and binds to beds, simulated monitors that prove their identity with a valid device signature, and that unauthenticated or tampered device data is rejected, verifying T425.
---

# T426: Verify that the authenticity of external devices/applications is properly checked

**Category:** CODE_FIX
**SD Elements:** [T426](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T426/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "Use pacientes fictícios e monitores simulados para mostrar frequência cardíaca, saturação, respiração, pressão arterial e um traçado sintético de ECG."
> (EN: Use fictional patients and simulated monitors to show heart rate, saturation, respiration, blood pressure and a synthetic ECG trace.)
> Source: specs/PRD.md, lines 29-31

**What the spec implies (naive approach):**
Device authenticity checks are easy to skip "because the monitors are only simulated", or to turn off with a debug flag that reaches production. These tests confirm that the checks from T425 run on every reading and every bed binding.

**Secure Implementation Pattern:**
```python
# backend/tests/test_device_auth.py
import json, time, uuid, pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.services.device_auth import SignedReading, verify_reading, DeviceAuthError

def sign(key, serial, payload, ts=None, nonce=None):
    body = {"device_serial": serial, "nonce": nonce or uuid.uuid4().hex,
            "ts": ts or int(time.time()), "payload": payload}
    msg = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return SignedReading(**body, signature=key.sign(msg).hex())

async def test_valid_reading_accepted(registered_device):
    key, serial = registered_device
    assert await verify_reading(sign(key, serial, {"spo2": 97})) == {"spo2": 97}

async def test_tampered_payload_rejected(registered_device):
    key, serial = registered_device
    r = sign(key, serial, {"spo2": 97}); r.payload["spo2"] = 70
    with pytest.raises(DeviceAuthError):
        await verify_reading(r)

@pytest.mark.parametrize("case", ["wrong_key", "unknown_serial", "stale", "replay", "retired"])
async def test_untrusted_devices_rejected(registered_device, case, make_case):
    with pytest.raises(DeviceAuthError):
        await verify_reading(await make_case(case, registered_device))

async def test_cannot_bind_unregistered_monitor(nurse_client):
    r = await nurse_client.post("/beds/B-101/monitor", json={"device_serial": "FAKE-999"})
    assert r.status_code in (403, 409)
```

**Implementation Guidance:**
- Automated: run the tests above in CI, and add an API-level test that `POST /internal/readings` with an unsigned body returns 401 and creates no alarm or reading row.
- Configuration guard: fail startup if a `DEVICE_AUTH_DISABLED` flag (or similar) is set when `APP_ENV=production`.
- Manual: in the simulation area, try to bind a monitor that is not in the device registry, and replay a captured reading request. Both must be rejected and appear in the audit log.
- Third-party components: list any external device or app integrations (currently none, all simulated). For each future integration, record the authenticity evidence (signed firmware, device certificate) and confirm that it is verified. Components without it must not feed critical vitals.
- Reference: SD Elements guidance for T426.

**Success Criteria:**
- [ ] All device-authenticity tests pass: valid accepted, and tampered, wrong-key, unknown, stale, replayed and retired rejected.
- [ ] Unregistered monitors cannot be bound to beds, and rejected attempts are audit-logged.

**Status:** Applied
