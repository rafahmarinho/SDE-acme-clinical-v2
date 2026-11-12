---
name: t175-test-that-the-client-validates-digital-certificate
description: Test recipe verifying ACME Clinical's backend HTTP clients (httpx, Supabase Python client) and frontend validate TLS certificates and refuse self-signed, expired or mismatched certificates when talking to Supabase and simulated integrations.
---

# T175: Test that the client validates digital certificates

**Category:** CODE_FIX
**SD Elements:** [T175](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T175/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "persistidos, com integrações externas simuladas. Organize o projeto em telas, componentes,"
> (EN: persisted, with simulated external integrations. Organize the project into screens, components,)
> Source: specs/PRD.md, line 9

**What the spec implies (naive approach):**
The FastAPI backend calls Supabase (REST, Auth, Storage) and possibly simulated integration endpoints. To get past local proxy or dev-certificate errors, developers set `verify=False` in httpx or `NODE_TLS_REJECT_UNAUTHORIZED=0`, which then ships to Vercel and allows man-in-the-middle of patient data and service role credentials. Client-certificate (mTLS) authentication is not used in this stack; the test focuses on server certificate validation by the clients.

**Secure Implementation Pattern:**
```python
# backend/app/db.py
import httpx
http = httpx.AsyncClient(verify=True, timeout=10.0)   # default CA bundle (certifi)

# backend/tests/test_tls_validation.py
import httpx, pytest

@pytest.mark.parametrize("url", [
    "https://self-signed.badssl.com/",
    "https://expired.badssl.com/",
    "https://wrong.host.badssl.com/",
    "https://untrusted-root.badssl.com/",
])
@pytest.mark.network
async def test_backend_client_rejects_bad_certificates(url):
    from app.db import http
    with pytest.raises(httpx.ConnectError):
        await http.get(url)

def test_no_tls_verification_disabled_in_source():
    import pathlib, re
    bad = re.compile(r"verify\s*=\s*False|CERT_NONE|NODE_TLS_REJECT_UNAUTHORIZED")
    for f in [*pathlib.Path("app").rglob("*.py")]:
        assert not bad.search(f.read_text()), f
```

**Implementation Guidance:**
- Create one shared `httpx.AsyncClient` in `backend/app/db.py` with default verification; pass it to the Supabase client and simulated integration services.
- Add the tests above under `backend/tests/` (mark network tests to run in CI nightly); also grep `frontend/` for `NODE_TLS_REJECT_UNAUTHORIZED`.
- Black-box check: route the backend through Burp/mitmproxy with its untrusted CA; calls to Supabase must fail with certificate errors and no data must be sent.
- Ensure all configured URLs (`SUPABASE_URL`, `VITE_API_BASE_URL`) use `https://` (validator in `backend/app/core/config.py`).
- Reference: SD Elements guidance for T175.

**Success Criteria:**
- [ ] Backend client raises on self-signed, expired, wrong-host and untrusted-root certificates.
- [ ] No `verify=False` or TLS-disabling flags in source or Vercel env.
- [ ] Proxy interception test documented with result (connections not established).
- [ ] Config rejects non-HTTPS service URLs in production.

**Status:** Applied
