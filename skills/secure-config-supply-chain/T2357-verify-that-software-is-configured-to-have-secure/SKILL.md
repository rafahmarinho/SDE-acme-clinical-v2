---
name: t2357-verify-that-software-is-configured-to-have-secure
description: Test recipe verifying ACME Clinical's default configuration is secure - production defaults disable API docs and debug, CORS is restrictive, headers are present, RLS is enabled everywhere, and settings are documented and version-controlled.
---

# T2357: Verify that software is configured to have secure settings by default

**Category:** CODE_FIX
**SD Elements:** [T2357](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2357/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "completo, configuração do banco, dados iniciais, exemplos de variáveis de ambiente e um"
> (EN: complete, database configuration, initial data, environment variable examples and a)
> Source: specs/PRD.md, line 47

**What the spec implies (naive approach):**
Without tests, insecure defaults creep back: someone adds `allow_origins=["*"]` to fix a CORS error, a new table is created without RLS, or a demo convenience flag defaults to on.

**Secure Implementation Pattern:**
```python
# backend/tests/test_secure_defaults.py
import importlib, pytest
from fastapi.testclient import TestClient

@pytest.fixture
def prod_client(monkeypatch):
    for var in ("APP_ENV", "ENABLE_DOCS", "ALLOWED_ORIGINS", "ALLOW_SIMULATION_RESET"):
        monkeypatch.delenv(var, raising=False)
    import app.core.config, app.main
    importlib.reload(app.core.config); importlib.reload(app.main)
    return TestClient(app.main.app)

def test_docs_disabled_by_default(prod_client):
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404

def test_cors_denies_unknown_origin(prod_client):
    r = prod_client.options("/health", headers={"Origin": "https://evil.example",
                                                "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers

def test_security_headers(prod_client):
    h = prod_client.get("/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert "strict-transport-security" in h

def test_reset_disabled_by_default(prod_client, admin_token):
    assert prod_client.post("/simulation/reset", headers=auth(admin_token)).status_code == 403
```

**Implementation Guidance:**
- Add the tests above under `backend/tests/`; add pgTAP `supabase/tests/rls_test.sql` asserting `relrowsecurity` is true for all `public` tables.
- Check deployed Vercel env matches the approved baseline in `docs/security/configuration.md` (manual checklist or `vercel env ls` review).
- Verify the configuration document lists purpose, options, default, security relevance and impact for each setting, and that changes go through PRs.
- Reference: SD Elements guidance for T2357.

**Success Criteria:**
- [ ] All secure-default tests pass with no env overrides.
- [ ] pgTAP RLS test passes.
- [ ] Deployed configuration matches the documented baseline.
- [ ] Configuration document is complete and under version control.

**Status:** Applied
