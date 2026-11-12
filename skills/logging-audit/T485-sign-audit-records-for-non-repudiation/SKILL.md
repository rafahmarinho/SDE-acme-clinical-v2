---
name: t485-sign-audit-records-for-non-repudiation
description: Signs and hash-chains ACME Clinical audit records for alarm acknowledgements, observations and threshold changes with an Ed25519/ECDSA server key so the acting clinician and time cannot be repudiated and tampering is detectable.
---

# T485: Sign audit records for non-repudiation

**Category:** CODE_FIX
**SD Elements:** [T485](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T485/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

> "acompanhar manutenção. Reconhecer um alarme não encerra uma condição que ainda está"
> (EN: track maintenance. Acknowledging an alarm does not end a condition that is still)
> Source: specs/PRD.md, line 35

**What the spec implies (naive approach):**
An `acknowledged_by` column on the alarm row, overwritable by later updates. A clinician could deny acknowledging an alarm, and anyone with DB access could rewrite who acknowledged what and when.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
import base64, hashlib, json
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA, EllipticCurvePrivateKey
from cryptography.hazmat.primitives import hashes, serialization
from app.core.config import settings

_KEY: EllipticCurvePrivateKey = serialization.load_pem_private_key(
    settings.audit_signing_key.encode(), password=None)          # P-521 key from Vercel env

def canonical(rec: dict) -> bytes:
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), default=str).encode()

def seal(record: dict, prev_hash: str) -> dict:
    body = {**record, "prev_hash": prev_hash, "key_id": settings.audit_key_id}
    digest = hashlib.sha512(canonical(body)).hexdigest()
    sig = _KEY.sign(canonical(body), ECDSA(hashes.SHA512()))
    return {**body, "record_hash": digest, "signature": base64.b64encode(sig).decode()}

# routers/alarms.py
# rec = {"action": "alarm.acknowledge", "alarm_id": a.id, "actor_id": user.id,
#        "session_id": claims["session_id"], "occurred_at": now_utc_ms()}
# prev = await db.last_audit_hash()   # inside a transaction w/ advisory lock
# await write_audit(db, seal(rec, prev), critical=True)
```

**Implementation Guidance:**
- Apply to actions requiring non-repudiation: alarm acknowledgement, observations, threshold changes, monitor-bed binding, maintenance sign-off, staff role changes.
- Sign with ECDSA P-521 + SHA-512 (or RSA-PSS SHA-512) using the `cryptography` package; private key stored only in Vercel env (`AUDIT_SIGNING_KEY`, never in repo or `.env.example` values); publish the public key with a `key_id` for verification and rotation.
- Bind the record to the user: include Supabase `auth.users.id`, JWT `session_id`, and a UTC ms timestamp; require a recent authentication (re-auth or fresh JWT) for acknowledgements. Note: true user-held private keys are out of scope for this demo; the server signature attests the authenticated session — document this limitation.
- Hash-chain (`prev_hash`) in the DB so deletion/reordering is detectable; serialize inserts with `pg_advisory_xact_lock` to keep the chain linear.
- Add `prev_hash`, `record_hash`, `signature`, `key_id` columns to `audit_events` (append-only per T350).
- Reference: SD Elements guidance for T485.

**Success Criteria:**
- [ ] Every acknowledgement audit row has a valid signature and chain link.
- [ ] A verifier script/service (`services/reports.py`) validates the full chain and reports breaks.
- [ ] Unit test: modifying any field of a sealed record fails verification.

**Status:** Applied
