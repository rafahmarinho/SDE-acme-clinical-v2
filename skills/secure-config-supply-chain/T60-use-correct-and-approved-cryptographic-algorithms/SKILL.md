---
name: t60-use-correct-and-approved-cryptographic-algorithms
description: Use only approved algorithms, parameters and key lengths in ACME Clinical (ECDSA P-521/SHA-512 audit signatures, HMAC-SHA256 integrity MACs, HKDF-SHA512 with purpose-separated keys, SHA-256 hashes, TLS 1.2+), with no encoding posing as encryption and no key reuse across purposes.
---

# T60: Use correct and approved cryptographic algorithms, parameters, and key lengths

**Category:** CODE_FIX
**SD Elements:** [T60](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T60/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "acompanhar manutenção. Reconhecer um alarme não encerra uma condição que ainda está"
> (EN: track maintenance. Acknowledging an alarm does not end a condition that is still)
> Source: specs/PRD.md, line 35

**What the spec implies (naive approach):**
Alarm acknowledgements, event history and alarm limits must be trustworthy in a clinical context, yet a naive build protects them with MD5 checksums, Base64-"encoded" secrets, one shared key for JWTs, MACs and signatures, or short HMAC keys. Those choices give no real integrity or confidentiality.

**Secure Implementation Pattern:**
```python
# backend/app/services/integrity.py
SIGNATURE_ALGORITHM = "ECDSA-P521-SHA512"
_CURVE = ec.SECP521R1()

def _derive(label: bytes, length: int) -> bytes:
    # one root secret -> independent keys per purpose (no key reuse)
    return HKDF(algorithm=hashes.SHA512(), length=length, salt=b"acme-clinical", info=label).derive(root)

audit_key  = _derive(b"acme.audit-signing.v1", 66)      # only if AUDIT_SIGNING_KEY is unset
config_key = _derive(b"acme.config-integrity.v1", 32)    # HMAC-SHA256, 256-bit key

# backend/app/core/security.py - pin the JWT algorithm; reject "none" and algorithm confusion
jwt.decode(token, key, algorithms=["HS256"], options={"require": ["exp", "sub"]})
```

**Implementation Guidance:**
- Approved set: SHA-256/SHA-512 (`hashlib`, pgcrypto `digest(..., 'sha256')`), HMAC-SHA256 with >= 256-bit keys, ECDSA P-521 or P-256 with SHA-2, HKDF-SHA512, AES-GCM if encryption is ever needed, TLS 1.2/1.3 (platform). Forbidden: MD5, SHA-1, DES/3DES, RC4, ECB mode, `alg=none`, Base64/gzip used as "encryption".
- Separate keys per purpose in `backend/app/services/integrity.py` (audit signing vs. config MAC vs. session IP hashing in `backend/app/routers/auth.py`); production should set dedicated `AUDIT_SIGNING_KEY` and `CONFIG_INTEGRITY_KEY` in Vercel rather than deriving from `SUPABASE_JWT_SECRET`.
- Enforce minimum key lengths at startup (`backend/app/core/config.py` `_production_secret_strength`: JWT secret and HMAC key >= 32 characters; signing key must be a P-521 EC key).
- Salted hashing of passwords is delegated to Supabase Auth (bcrypt); device secrets are high-entropy random values, so SHA-256 without a salt is acceptable for them (`verify_monitor_secret`).
- Record algorithms and key sizes in `docs/security/secure-config.md` and expose the audit public key via `GET /v1/events/signing-key`.
- Reference: SD Elements guidance for T60.

**Success Criteria:**
- [ ] `backend/tests/test_secure_config.py::test_t445_no_weak_primitives_and_explicit_jwt_algorithms` passes (no `md5`, `sha1`, `DES`, `ECB`, `random` for keys).
- [ ] `test_t445_alg_none_and_wrong_keys_are_rejected` and `test_t445_jwt_secret_meets_key_length_in_production` pass.
- [ ] `backend/tests/test_logging_audit.py::test_t485_records_are_signed_with_ecdsa_p521_sha512_and_verify` passes.
- [ ] Pytest: the derived audit and config keys differ from each other and from the JWT secret.

**Status:** Applied
