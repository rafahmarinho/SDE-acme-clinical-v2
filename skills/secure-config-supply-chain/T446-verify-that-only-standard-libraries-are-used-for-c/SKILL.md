---
name: t446-verify-that-only-standard-libraries-are-used-for-c
description: Test recipe verifying ACME Clinical uses only standard, maintained cryptographic libraries (Supabase Auth, PyJWT/cryptography, hashlib/hmac/secrets, Web Crypto) with no custom crypto and no known vulnerabilities.
---

# T446: Verify that only standard libraries are used for cryptography

**Category:** CODE_FIX
**SD Elements:** [T446](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T446/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current and stable versions of the technologies and Supabase for PostgreSQL, email and)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
Email/password login is delegated to Supabase Auth, but the FastAPI backend must verify Supabase JWTs and may sign cron/report URLs. Developers sometimes hand-roll JWT decoding (base64 split without signature check) or pick unmaintained packages such as `python-jose` or `pycrypto`.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
import jwt                      # PyJWT
from jwt import PyJWKClient
from app.core.config import settings

_jwks = PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")

def verify_supabase_jwt(token: str) -> dict:
    key = _jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["ES256", "RS256"],
                      audience="authenticated",
                      issuer=f"{settings.supabase_url}/auth/v1")
```

```python
# backend/tests/test_crypto_libraries.py
import pathlib, re
BANNED = re.compile(r"^\s*(import|from)\s+(jose|Crypto|pycrypto|simplecrypt|md5)\b", re.M)

def test_no_nonstandard_crypto_libraries():
    for f in pathlib.Path("app").rglob("*.py"):
        assert not BANNED.search(f.read_text()), f
```

**Implementation Guidance:**
- List crypto use: password hashing (Supabase Auth, bcrypt), JWT verification (PyJWT), HMAC signing (`hmac` + `hashlib.sha256`), random (`secrets`), TLS (httpx/certifi), frontend (`@supabase/supabase-js`, Web Crypto only).
- Record the list in `docs/security/crypto-inventory.md` with versions.
- Pin `PyJWT[crypto]` and `cryptography` in `backend/requirements.txt` / lockfile; run `pip-audit` and `pnpm audit` to confirm no outstanding CVEs (T241).
- Fail CI on banned imports (test above) and on npm crypto polyfills like `crypto-js` in `frontend/package.json`.
- Reference: SD Elements guidance for T446.

**Success Criteria:**
- [ ] Crypto inventory documented with library and version.
- [ ] No custom or banned crypto libraries in backend or frontend.
- [ ] `pip-audit` and `pnpm audit` report no known vulnerabilities in crypto libraries.
- [ ] JWT verification uses PyJWT with explicit algorithm allow-list.

**Status:** Applied
