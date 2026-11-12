---
name: t1365-mitigate-server-side-request-forgery
description: Mitigate SSRF in the ACME Clinical FastAPI backend by restricting all outbound HTTP calls (Supabase Auth/Storage, simulated integrations) to a fixed allowlist of HTTPS hosts from configuration, never fetching user-supplied URLs, and validating responses.
---

# T1365: Mitigate Server Side Request Forgery

**Category:** CODE_FIX
**SD Elements:** [T1365](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T1365/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "persistidos, com integrações externas simuladas. Organize o projeto em telas, componentes,"
> (EN: persisted, with simulated external integrations. Organize the project into screens, components,)
> Source: specs/PRD.md, line 9

**What the spec implies (naive approach):**
"Simulated external integrations" and file handling tempt developers to add endpoints such as "import monitor data from URL", "webhook callback URL" or "fetch attachment from link" that pass a client-supplied URL to `httpx.get()`. From inside Vercel/Supabase this can reach cloud metadata endpoints, internal Supabase services with the service-role key attached, or non-HTTP schemes.

**Secure Implementation Pattern:**
```python
# backend/app/services/outbound.py (or helpers inside services/privacy.py / files.py)
from urllib.parse import urlsplit
import httpx
from app.core.config import get_settings

def _allowed_hosts() -> frozenset[str]:
    s = get_settings()
    return frozenset({urlsplit(str(s.supabase_url)).hostname})   # exact hosts from config only

def checked_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in _allowed_hosts() or parts.port not in (None, 443):
        raise ValueError("outbound destination not allowed")
    if parts.username or parts.password:
        raise ValueError("credentials in URL not allowed")
    return url

def outbound_client() -> httpx.AsyncClient:
    # no redirects: a 302 to 169.254.169.254 must not be followed
    return httpx.AsyncClient(follow_redirects=False, timeout=httpx.Timeout(5.0), verify=True)

async def get_json(path: str) -> dict:
    url = checked_url(f"{get_settings().supabase_url}{path}")      # path is code-defined, not user input
    async with outbound_client() as c:
        r = await c.get(url)
    if r.headers.get("content-type", "").split(";")[0] != "application/json":
        raise ValueError("unexpected upstream response")
    return r.json()
```

**Implementation Guidance:**
- Inventory every `httpx` use (`backend/app/services/privacy.py` `_supabase_client`, Supabase Storage calls from `backend/app/services/files.py` and `backend/app/routers/files.py`); each must target a host derived from `Settings` in `backend/app/core/config.py`, never from request data.
- Do not add any endpoint that accepts a URL to fetch. Simulated integrations live in `backend/app/services/simulation.py` and must stay in-process (no outbound calls driven by scenario input).
- Allow only `https`; block other schemes; disable redirects (`follow_redirects=False`); set short timeouts; keep TLS verification on (T156).
- Validate upstream responses (content type, Pydantic model) before returning anything to the client; never proxy raw upstream bodies or error messages.
- Signed Storage URLs are generated server-side for objects whose paths come from `safe_object_path` in `backend/app/services/files.py`, not from the client.
- Reference: SD Elements guidance for T1365.

**Success Criteria:**
- [ ] No router accepts a parameter that is used as an outbound URL or host.
- [ ] Unit test (`backend/tests/test_input_validation.py`): `checked_url` rejects `http://`, `file://`, `gopher://`, `https://169.254.169.254/`, `https://evil.example/`, `https://user:pw@<supabase-host>/`.
- [ ] All outbound clients use `follow_redirects=False`, TLS verification and timeouts.

**Status:** Applied
