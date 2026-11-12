---
name: t1392-test-for-server-side-request-forgery
description: Test recipe verifying that the ACME Clinical FastAPI backend never fetches user-supplied URLs (simulated external integrations, device endpoints, avatars, webhooks) and blocks loopback, metadata and non-HTTP schemes, including blind SSRF.
---

# T1392: Test for Server Side Request Forgery

**Category:** CODE_FIX
**SD Elements:** [T1392](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1392/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "persistidos, com integrações externas simuladas. Organize o projeto em telas, componentes,"
> (EN: "persisted, with simulated external integrations. Organize the project into screens, components,")
> Source: specs/PRD.md, line 9

**What the spec implies (naive approach):**
"Simulated external integrations" could tempt a developer to let administrators configure an integration/monitor endpoint URL, a profile avatar URL, or a report webhook that the backend then fetches with `httpx.get(url)`. On Vercel, that can reach internal services or metadata endpoints. The design goal is that the API fetches no user-supplied URL; this test proves it.

**Secure Implementation Pattern:**
```python
# backend/tests/test_ssrf.py
import pytest, respx, httpx

PAYLOADS = ["http://127.0.0.1:80", "http://169.254.169.254/latest/meta-data/",
            "http://localhost/server-status", "file:///etc/passwd", "gopher://127.0.0.1:6379/_INFO",
            "dict://127.0.0.1:11211/", "http://[::1]/", "http://0x7f000001/",
            "aHR0cDovLzEyNy4wLjAuMTo4MA=="]  # base64 of http://127.0.0.1:80

URL_FIELDS = [("put", "/api/devices/{id}", "integration_url"),
              ("patch", "/api/profile", "avatar_url"),
              ("post", "/api/reports", "callback_url")]

@pytest.mark.asyncio
@respx.mock(assert_all_mocked=True)          # any outbound HTTP call raises
@pytest.mark.parametrize("method,path,field", URL_FIELDS)
@pytest.mark.parametrize("payload", PAYLOADS)
async def test_no_outbound_fetch(client, admin_headers, device_id, method, path, field, payload):
    r = await getattr(client, method)(path.format(id=device_id), json={field: payload}, headers=admin_headers)
    assert r.status_code in (404, 422)        # field not accepted / route absent
    assert respx.calls.call_count == 0
```

**Implementation Guidance:**
- Identify inputs that could carry a URL or host: device/integration config, profile avatar, report export/callback, file import, any header used to build URLs.
- Submit loopback, cloud-metadata, alternative encodings (decimal/hex IP, IPv6, base64) and other schemes (`file`, `gopher`, `dict`, `sftp`); verify no outbound request occurs (respx/mocked transport) and no internal data is returned.
- Blind SSRF: in a staging deployment, submit a Burp Collaborator/own VPS domain and confirm no callbacks in its logs.
- Control: simulated integrations in `backend/app/services/simulation.py` run in-process; files go to Supabase Storage via the server-configured client; avatars use Storage uploads, not URLs. If an outbound URL is ever required, use a fixed allow-list of hosts from env config, HTTPS only, and resolve-then-block private IP ranges.
- Reference: SD Elements guidance for T1392.

**Success Criteria:**
- [ ] `backend/tests/test_ssrf.py` passes with zero outbound calls recorded.
- [ ] Out-of-band test against staging shows no callback requests.
- [ ] Code search finds no `httpx`/`requests` call whose URL derives from request data.

**Status:** Applied
