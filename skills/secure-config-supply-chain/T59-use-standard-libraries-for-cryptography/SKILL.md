---
name: t59-use-standard-libraries-for-cryptography
description: Restrict ACME Clinical cryptography to vetted libraries - pyca/cryptography, PyJWT, Python hashlib/hmac/secrets, PostgreSQL pgcrypto, Supabase Auth and Web Crypto - and forbid hand-rolled hashing, signing, encryption or password storage.
---

# T59: Use standard libraries for cryptography

**Category:** CODE_FIX
**SD Elements:** [T59](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T59/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: Use current, stable versions of the technologies and Supabase for PostgreSQL, e-mail and password login, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
Features such as monitor authentication, tamper-evident events and alarm-limit integrity invite quick custom code: XOR "encryption", a home-made HMAC (`sha256(key + msg)`), manual JWT parsing with `base64` and `json`, or storing passwords in a custom table. Such implementations are prone to length-extension, timing and padding flaws.

**Secure Implementation Pattern:**
```python
# backend/app/services/integrity.py - vetted primitives only
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import hmac, hashlib

def sign(payload: dict) -> str:
    sig = _signing_key().sign(canonical(payload), ec.ECDSA(hashes.SHA512()))
    return base64.b64encode(sig).decode()

def config_mac_valid(kind: str, payload: dict, mac: str | None) -> bool:
    expected = hmac.new(_config_key(), kind.encode() + b"|" + canonical(payload), hashlib.sha256).hexdigest()
    return bool(mac) and hmac.compare_digest(str(mac), expected)

# backend/app/core/security.py - PyJWT verifies Supabase tokens; never decode JWTs by hand
claims = jwt.decode(token, key, algorithms=["HS256"], audience=settings.supabase_jwt_audience)
```

**Implementation Guidance:**
- Allowed crypto dependencies: `cryptography`, `pyjwt[crypto]` (pinned in `backend/requirements.txt`), Python stdlib `hashlib`/`hmac`/`secrets`, PostgreSQL `pgcrypto` (`digest`, `gen_random_uuid` in `supabase/migrations/*.sql`), and browser Web Crypto. No other crypto packages (e.g. `pycrypto`, `crypto-js`).
- Passwords are stored and verified only by Supabase Auth (bcrypt); the app never hashes user passwords itself (`backend/app/services/passwords.py` only checks policy).
- Use library constant-time comparisons (`hmac.compare_digest`) as in `backend/app/services/device_auth.py` and `integrity.py`.
- Audit signatures (`backend/app/core/audit.py` -> `integrity.sign`) and the event hash chain (`event_row_hash` in `0004_ops_audit_resilience.sql`) use library primitives only.
- Document the approved list in `docs/security/secure-config.md`.
- Reference: SD Elements guidance for T59.

**Success Criteria:**
- [ ] `backend/tests/test_secure_config.py::test_t446_only_standard_crypto_libraries` passes (fails on any non-approved crypto import or a manual JWT split/decode).
- [ ] `backend/tests/test_authentication.py::test_no_hand_rolled_password_hashing_or_auth_rows` passes.
- [ ] `frontend/package.json` contains no third-party crypto library (checked by a test).

**Status:** Applied
