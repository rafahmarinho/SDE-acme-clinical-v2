---
name: t425-check-the-authenticity-of-external-devices-applica
description: Gives each ACME Clinical simulated patient monitor a registered device identity (serial plus Ed25519 public key) and requires signed, fresh readings before a monitor can be bound to a bed or its vitals accepted, so real devices can later plug in with manufacturer-backed authenticity checks.
---

# T425: Check the authenticity of external devices/applications

**Category:** CODE_FIX
**SD Elements:** [T425](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T425/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e acompanhar manutenção."
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and tracking maintenance.)
> Source: specs/PRD.md, lines 33-35

**What the spec implies (naive approach):**
Monitors are simulated, so a developer would let any request carrying `{"monitor_id": "MON-03", "spo2": 88}` write readings, and let staff bind any monitor ID to a bed. A forged or cloned "monitor" could then inject false vitals or suppress alarms for a patient. In a clinical system that is a safety issue.

**Secure Implementation Pattern:**
```python
# backend/app/services/device_auth.py
import json, time
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from pydantic import BaseModel

MAX_SKEW_S = 30

class SignedReading(BaseModel):
    device_serial: str
    nonce: str
    ts: int
    payload: dict           # hr, spo2, rr, bp, ecg samples
    signature: str          # hex Ed25519 over canonical JSON of the fields above

async def verify_reading(r: SignedReading) -> dict:
    dev = await db.fetchrow("select public_key_pem, status from devices where serial=$1", r.device_serial)
    if dev is None or dev["status"] != "active":
        raise DeviceAuthError("unknown or inactive device")
    if abs(time.time() - r.ts) > MAX_SKEW_S or not await nonces.add_once(r.device_serial, r.nonce):
        raise DeviceAuthError("stale or replayed reading")
    msg = json.dumps({"device_serial": r.device_serial, "nonce": r.nonce, "ts": r.ts,
                      "payload": r.payload}, sort_keys=True, separators=(",", ":")).encode()
    try:
        load_pem_public_key(dev["public_key_pem"].encode()).verify(bytes.fromhex(r.signature), msg)
    except (InvalidSignature, ValueError):
        raise DeviceAuthError("bad signature")
    return r.payload
```

**Implementation Guidance:**
- Add a `devices` table in `supabase/migrations/0001_schema.sql` with `serial` (unique), `manufacturer`, `public_key_pem`, `status` (`pending`/`active`/`retired`) and `registered_by`. Only biomedical technicians or administrators can activate a device after checking its identity, and the action is audit-logged.
- The simulator (`backend/app/services/simulation.py`) holds one Ed25519 private key per simulated monitor in a server-only secret, not in the DB or the repo, and signs every reading. Ingestion calls `verify_reading` before storing data or evaluating alarms (`backend/app/services/alarms.py`).
- Bed binding (`POST /beds/{id}/monitor`) is allowed only for `active` devices that recently sent a valid signed heartbeat. Reject unknown or unsigned devices.
- For future real monitors: require a manufacturer-signed device certificate (unique ID plus manufacturer key) and verify the chain at registration. Do not use components without proof of authenticity for critical vitals.
- Reference: SD Elements guidance for T425.

**Success Criteria:**
- [ ] Readings with a bad signature, an unknown serial, a stale timestamp or a replayed nonce are rejected and never trigger or clear alarms.
- [ ] Binding an unregistered or retired monitor to a bed fails with 409 or 403.
- [ ] `backend/tests/test_device_auth.py` covers valid, tampered-payload, wrong-key, replay and stale cases.

**Status:** Pending
