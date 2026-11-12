---
name: t96-test-if-your-site-is-vulnerable-to-csrf
description: Tests that high-value ACME Clinical actions (acknowledge alarm, bind monitor to bed, record observation, change limits, reset simulation, manage team) cannot be forged cross-site, validating the Bearer-token plus strict-CORS plus JSON-only CSRF defense.
---

# T96: Test if your site is vulnerable to CSRF

**Category:** CODE_FIX
**SD Elements:** [T96](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T96/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados."
> (EN: choose scenarios, advance the simulation, view events and reset the data.)
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
Actions such as "reset data", "advance simulation" and "acknowledge alarm" are easy to expose as simple GET links or form posts. If any of them accepts a cookie or a form-encoded/simple request, a malicious page visited by a logged-in clinician could trigger them.

**Secure Implementation Pattern:**
```python
# backend/tests/test_csrf.py
import pytest

HIGH_VALUE = [("POST", "/api/alarms/demo-alarm-1/acknowledge"),
              ("POST", "/api/monitors/demo-mon-1/bind"),
              ("POST", "/api/patients/demo-1/observations"),
              ("PUT",  "/api/limits/demo-1"),
              ("POST", "/api/simulation/demo-run/reset"),
              ("POST", "/api/simulation/demo-run/advance")]

@pytest.mark.anyio
@pytest.mark.parametrize("method,path", HIGH_VALUE)
async def test_form_post_without_bearer_rejected(client, method, path):
    # what an attacker <form> can send: simple content type, cookies only, no Authorization
    r = await client.request(method, path, data={"note": "x"},
        headers={"Origin": "https://evil.example", "Cookie": "sb-access-token=stolen"})
    assert r.status_code in (401, 403, 415)

@pytest.mark.anyio
@pytest.mark.parametrize("method,path", HIGH_VALUE)
async def test_form_encoded_with_token_rejected(client, method, path, auth_headers):
    r = await client.request(method, path, data={"note": "x"}, headers=auth_headers)
    assert r.status_code == 415

@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/api/simulation/demo-run/reset", "/api/alarms/demo-alarm-1/acknowledge"])
async def test_no_state_change_via_get(client, path, auth_headers):
    assert (await client.get(path, headers=auth_headers)).status_code == 405
```

**Implementation Guidance:**
- Add `backend/tests/test_csrf.py`; it verifies the defense chosen in T1541 and complements the CORS tests in T318.
- Manual Method Two: host an HTML page on another origin with an auto-submitting `<form method="POST" action="https://<api>/api/simulation/<run-id>/reset">` and a `fetch(..., {mode: "no-cors"})`; log into ACME Clinical in the same browser and open the page. The test fails if the simulation resets or the alarm is acknowledged.
- Manual Method One: replay a captured request with the `Authorization` header removed (only cookies kept); it must return 401.
- Reference: SD Elements guidance for T96.

**Success Criteria:**
- [ ] `backend/tests/test_csrf.py` passes for every high-value action.
- [ ] Manual cross-origin form/fetch attempt produces no state change (verify via simulation events log).

**Status:** Applied
