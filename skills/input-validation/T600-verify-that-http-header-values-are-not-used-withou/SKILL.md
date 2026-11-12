---
name: t600-verify-that-http-header-values-are-not-used-withou
description: Test recipe verifying that ACME Clinical never uses Host, X-Forwarded-Host or Referer header values for authentication, link generation (password reset, invites) or user-visible output without validation.
---

# T600: Verify that HTTP header values are not used without proper validation

**Category:** CODE_FIX
**SD Elements:** [T600](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T600/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Password recovery and staff management generate links, and the API logs and may echo request metadata. Without a test, host-header poisoning or Referer-based checks can be introduced unnoticed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_header_trust.py
import pytest

@pytest.mark.asyncio
async def test_untrusted_host_rejected(client):
    r = await client.get("/api/health", headers={"Host": "evil.example"})
    assert r.status_code == 400

@pytest.mark.asyncio
async def test_invite_link_ignores_forwarded_host(client, admin_headers, outbox, settings):
    await client.post("/api/staff", headers={**admin_headers, "X-Forwarded-Host": "evil.example"},
                      json={"full_name": "Dr Test", "email": "dr@demo.test", "role": "physician"})
    assert "evil.example" not in outbox[-1].body
    assert str(settings.frontend_url).rstrip("/") in outbox[-1].body

@pytest.mark.asyncio
async def test_referer_is_not_auth(client):
    r = await client.post("/api/simulation/reset",
                          headers={"Referer": "https://acme-clinical.vercel.app/simulation"})
    assert r.status_code == 401

@pytest.mark.asyncio
async def test_header_not_reflected(client, nurse_headers):
    r = await client.get("/api/profile", headers={**nurse_headers, "User-Agent": "<script>x</script>"})
    assert "<script>" not in r.text
```

**Implementation Guidance:**
- Review `backend/app` for reads of `request.headers` (`host`, `referer`, `origin`, `x-forwarded-*`, `user-agent`) and `request.base_url`; each must be validated or used only for logging.
- Test with forged Host / X-Forwarded-Host values on endpoints that produce links (staff invites, report share links) and confirm configured URLs are used (Supabase password recovery uses `VITE_APP_URL` + Supabase allow-list; verify too).
- Confirm Referer/Origin never grant access: privileged actions without a valid JWT must fail.
- Confirm header values are not reflected unencoded in responses or rendered in admin log views.
- Reference: SD Elements guidance for T600.

**Success Criteria:**
- [ ] `backend/tests/test_header_trust.py` passes.
- [ ] Code review checklist entry confirms no header-derived values in links, auth or output.

**Status:** Pending
