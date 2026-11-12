---
name: t2300-verify-that-a-secure-application-architecture-is-d
description: Test recipe verifying ACME Clinical's web, API and data layers are separated on Vercel and Supabase, that the browser cannot bypass the API to modify protected data, and that platform scaling, CDN and redundancy are in place.
---

# T2300: Verify that a secure application architecture is designed for the cloud environment (Cloud)

**Category:** CODE_FIX
**SD Elements:** [T2300](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2300/)
**Priority:** 10/10 · **Phase:** testing

**Spec Context:**
> "README com os passos para rodar e publicar a versão web e a API na Vercel. Confira os fluxos"
> (EN: README with the steps to run and publish the web version and the API on Vercel. Check the main)
> Source: specs/PRD.md, line 49

**What the spec implies (naive approach):**
Two Vercel deployments look layered, but nobody verifies that the anon key cannot write alarms or readings directly, or that the API is the only path to privileged operations.

**Secure Implementation Pattern:**
```python
# backend/tests/test_layer_separation.py  (runs against a Supabase test project)
import os, pytest
from supabase import create_client

anon = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

@pytest.mark.parametrize("table,row", [
    ("readings", {"patient_ref": "PT-test", "heart_rate": 80}),
    ("alarm_events", {"patient_ref": "PT-test", "kind": "low_spo2"}),
    ("security_settings", {"allow_simulation_reset": True}),
])
def test_browser_key_cannot_write_protected_tables(table, row, nurse_session):
    anon.auth.set_session(nurse_session.access_token, nurse_session.refresh_token)
    with pytest.raises(Exception):
        anon.table(table).insert(row).execute()

def test_frontend_bundle_has_no_service_key():
    bundle = "".join(p.read_text() for p in __import__("pathlib").Path("../frontend/dist").rglob("*.js"))
    assert os.environ["SUPABASE_SERVICE_ROLE_KEY"] not in bundle
```

**Implementation Guidance:**
- Verify the three layers from T2288 exist as separate deployments/services and match `docs/architecture.md`.
- Run the tests above against a disposable Supabase project/branch in CI.
- Verify platform features (manual checklist): Vercel CDN and automatic scaling for frontend and functions; function region aligned with Supabase region; Supabase backups/PITR enabled; Vercel Firewall/attack challenge mode available for DDoS.
- Reference: SD Elements guidance for T2300.

**Success Criteria:**
- [ ] Anon/authenticated browser key cannot write protected tables.
- [ ] Service role key absent from the frontend bundle.
- [ ] Architecture document matches deployed projects.
- [ ] Platform scaling/CDN/backup checklist completed and recorded.

**Status:** Pending
