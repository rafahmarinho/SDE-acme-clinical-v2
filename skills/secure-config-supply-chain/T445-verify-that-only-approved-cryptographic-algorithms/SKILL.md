---
name: t445-verify-that-only-approved-cryptographic-algorithms
description: Test recipe verifying ACME Clinical uses only approved algorithms and key sizes (ES256/RS256 JWTs, HMAC-SHA256, AES-GCM, TLS 1.2+) and rejects weak options such as alg=none, HS256 with short secrets, MD5/SHA1 or ECB.
---

# T445: Verify that only approved cryptographic algorithms and key lengths are used

**Category:** CODE_FIX
**SD Elements:** [T445](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T445/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current and stable versions of the technologies and Supabase for PostgreSQL, email and)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
JWT verification is often written with `algorithms=None` or accepts whatever `alg` the token header says, and signed links use MD5 or SHA1. If any field-level encryption is added, ECB mode or static IVs are common mistakes.

**Secure Implementation Pattern:**
```python
# backend/tests/test_approved_algorithms.py
import jwt, pytest, pathlib, re
from app.core.security import verify_supabase_jwt

def test_alg_none_rejected():
    forged = jwt.encode({"sub": "x", "aud": "authenticated"}, key="", algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        verify_supabase_jwt(forged)

def test_hs256_with_guessable_secret_rejected():
    forged = jwt.encode({"sub": "x", "aud": "authenticated"}, "secret", algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        verify_supabase_jwt(forged)

WEAK = re.compile(r"hashlib\.(md5|sha1)\(|modes\.ECB|DES|RC4|algorithms=None")

def test_no_weak_primitives_in_source():
    for f in pathlib.Path("app").rglob("*.py"):
        assert not WEAK.search(f.read_text()), f
```

```python
# if field encryption is ever needed: AES-256-GCM with random 96-bit nonce
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)
```

**Implementation Guidance:**
- List algorithms in `docs/security/crypto-inventory.md`: Supabase Auth password hashing (bcrypt), JWT ES256/RS256 (or HS256 only with Supabase's 256-bit+ secret held server-side), HMAC-SHA256 for cron/signed URLs, TLS 1.2+ (Vercel/Supabase managed).
- Compare against FIPS 140-3 approved algorithms; prefer AES-GCM (authenticated) over CBC, and never ECB or static IVs.
- Implement the tests above in `backend/tests/`; enforce `algorithms=[...]` explicitly in `backend/app/core/security.py`.
- Reference: SD Elements guidance for T445.

**Success Criteria:**
- [ ] `alg=none` and wrong-algorithm tokens are rejected.
- [ ] No MD5/SHA1/DES/RC4/ECB use in source.
- [ ] Symmetric keys are at least 256 bits; nonces are random per message.
- [ ] Algorithm inventory documented and reviewed.

**Status:** Applied
