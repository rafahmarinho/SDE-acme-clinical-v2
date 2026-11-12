---
name: t98-test-for-input-validation-on-a-server
description: Test recipe confirming that ACME Clinical inputs validated in the React UI are also validated by the FastAPI server when converted to invalid values with a proxy or direct API calls.
---

# T98: Test for input validation on a server

**Category:** CODE_FIX
**SD Elements:** [T98](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T98/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you may create something very visual in 3D if")
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Limit settings, staff management and simulation controls will have client-side validation, so values look validated during normal use. The test must prove the server still rejects the same values when the UI is bypassed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_server_validation.py
import pytest

CASES = [
    ("put", "/api/settings/limits", {"hr_low": 40, "hr_high": 999, "spo2_low": 90,
                                      "rr_low": 8, "rr_high": 30, "sys_low": 90, "sys_high": 160}),
    ("put", "/api/settings/limits", {"hr_low": "40", "hr_high": 120}),           # wrong type
    ("post", "/api/staff", {"full_name": "A" * 500, "email": "x", "role": "root"}),
    ("post", "/api/simulation/advance", {"steps": -5}),
    ("post", "/api/simulation/scenario", {"monitor_id": "not-a-uuid", "scenario": "explode"}),
]

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", CASES)
async def test_server_rejects_invalid(client, admin_headers, method, path, body):
    r = await getattr(client, method)(path, json=body, headers=admin_headers)
    assert r.status_code == 422
    assert r.json() == {"error": "Invalid request."} or "detail" in r.json()
```

**Implementation Guidance:**
- Enumerate HTTP parameters and cookies that the UI validates (limits form, staff form, search box length, simulation step count, date ranges for reports).
- Enter a valid value in the UI, intercept with an HTTP proxy, and change it to an invalid value (out of range, wrong type, oversized, unknown enum); repeat with automated pytest/httpx cases above.
- The test fails if the server accepts or persists the invalid value.
- Reference: SD Elements guidance for T98.

**Success Criteria:**
- [ ] `backend/tests/test_server_validation.py` covers each form-backed endpoint and passes.
- [ ] Manual proxy run documented for limits, staff and simulation screens with all tampered values rejected.

**Status:** Applied
