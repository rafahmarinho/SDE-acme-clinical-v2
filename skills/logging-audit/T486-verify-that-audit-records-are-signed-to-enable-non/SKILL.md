---
name: t486-verify-that-audit-records-are-signed-to-enable-non
description: Tests that ACME Clinical audit records for alarm acknowledgements and other clinical actions carry valid SHA-512 ECDSA signatures, identifiers, UTC timestamps and an unbroken hash chain.
---

# T486: Verify that audit records are signed to enable non-repudiation

**Category:** CODE_FIX
**SD Elements:** [T486](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T486/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Without a test, signing may be skipped for some routes, use a weak hash, or omit the actor/timestamp from the signed payload, leaving acknowledgements repudiable.

**Secure Implementation Pattern:**
```python
# backend/tests/test_audit_signatures.py
import base64, hashlib, pytest
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature
from app.core.security import canonical

SIGNED_ACTIONS = {"alarm.acknowledge", "observation.create", "threshold.update", "monitor.bind"}

def verify(row, pub):
    body = {k: v for k, v in row.items() if k not in ("id", "record_hash", "signature")}
    assert hashlib.sha512(canonical(body)).hexdigest() == row["record_hash"]
    pub.verify(base64.b64decode(row["signature"]), canonical(body), ECDSA(hashes.SHA512()))

def test_signed_rows_valid_and_chained(audit_rows_ordered, audit_public_key):
    prev = None
    for row in audit_rows_ordered():
        if row["action"] in SIGNED_ACTIONS:
            assert row["actor_id"] and row["occurred_at"] and row["key_id"]
            verify(row, audit_public_key)
        if prev:
            assert row["prev_hash"] == prev["record_hash"]
        prev = row

def test_tampered_row_detected(sealed_ack_row, audit_public_key):
    sealed_ack_row["actor_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises((InvalidSignature, AssertionError)):
        verify(sealed_ack_row, audit_public_key)
```

**Implementation Guidance:**
- Generate a demo flow (scenario low saturation, acknowledge alarm, add observation, change threshold, bind monitor), then fetch `audit_events` ordered by `id`.
- Verify each non-repudiation action has signature, `key_id`, actor ID, session ID and UTC timestamp inside the signed payload.
- Confirm algorithm is SHA-512 with ECDSA (or RSA) — reject SHA-1/MD5 or HMAC-only.
- Verify chain continuity and that tampering of any field or deletion of a row is detected.
- Reference: SD Elements guidance for T486.

**Success Criteria:**
- [ ] `backend/tests/test_audit_signatures.py` passes for the demo flow.
- [ ] Tamper and deletion tests fail verification as expected.
- [ ] Algorithm and key ID documented in README security section.

**Status:** Applied
