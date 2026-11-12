---
name: t83-verify-transactional-authorization-and-screening
description: Verify that ACME Clinical high-sensitivity actions (alarm limit changes, simulation reset, staff role changes, break-glass) demand re-authentication, are blocked for revoked accounts and that anomalous requests are held for review.
---

# T83: Verify transactional authorization and screening

**Category:** CODE_FIX
**SD Elements:** [T83](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T83/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you can create something very visual in 3D if")
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Without verification, the step-up and screening controls from T9 may exist only on the frontend dialog. The guidance mentions credit cards; ACME Clinical has no payments, so the blacklist test applies to revoked staff accounts and the "high value" set is patient-safety actions.

**Secure Implementation Pattern:**
```python
# backend/tests/test_sensitive_transactions.py
SENSITIVE = [
    ("PUT", "/api/thresholds/{tid}", "physician", {"spo2_low": 90}),
    ("POST", "/api/simulation/reset", "administrator", {"confirm": "RESET"}),
    ("PATCH", "/api/staff/{sid}/role", "administrator", {"role": "physician"}),
]

@pytest.mark.parametrize("method,path,role,body", SENSITIVE)
async def test_stale_session_requires_step_up(client_as, ids, method, path, role, body):
    c = client_as(role, auth_age_minutes=30)
    r = await c.request(method, path.format(**ids), json=body)
    assert r.status_code == 401 and "step_up_required" in r.headers["WWW-Authenticate"]

async def test_revoked_account_blocked(client_as, revoke, physician, ids):
    await revoke(physician.id)
    r = await client_as(physician, auth_age_minutes=0).put(f"/api/thresholds/{ids['tid']}", json={"spo2_low": 90})
    assert r.status_code == 403

async def test_anomalous_change_held(client_as, ids):
    c = client_as("physician", auth_age_minutes=0)
    r = await c.put(f"/api/thresholds/{ids['tid']}", json={"spo2_low": 60})
    assert r.status_code == 409

async def test_country_jump_flagged(client_as, ids):
    c = client_as("administrator", auth_age_minutes=0)
    await c.get("/api/me", headers={"x-vercel-ip-country": "BR"})
    r = await c.post("/api/simulation/reset", json={"confirm": "RESET"}, headers={"x-vercel-ip-country": "RU"})
    assert r.status_code in (401, 409)
```

**Implementation Guidance:**
- Agree the list of high-sensitivity actions with the team (T9) and keep it as the test parameter set.
- Verify re-authentication is enforced server-side by sending requests with an old `amr` timestamp, bypassing the UI.
- Add entries to the revocation list and confirm actions fail.
- Build a small test plan with the anomaly rules: implausible thresholds, bursts of changes, geo changes, off-hours resets; confirm each is rejected or held and audited.
- Malware/malicious script detection: not applicable as a server feature here; verify the CSP header on the Vercel frontend instead.
- Reference: SD Elements guidance for T83.

**Success Criteria:**
- [ ] All tests above pass in `backend/tests/test_sensitive_transactions.py`.
- [ ] Each held/blocked action appears in the audit log with reason.
- [ ] CSP header present on the deployed frontend (manual check recorded).

**Status:** Applied
