---
name: t1039-test-that-homoglyphs-are-distinguishable-in-the-ap
description: Test recipe submitting regular and homoglyph versions of staff names, emails and patient identifiers to ACME Clinical and verifying the two are distinguishable (rejected, flagged or Punycode-encoded) in screens, audit views and reports.
---

# T1039: Test that homoglyphs are distinguishable in the application's output

**Category:** CODE_FIX
**SD Elements:** [T1039](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1039/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you may create something very visual in 3D if")
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Staff lists, alarm acknowledgement history, observation authors and reports display user-provided names and identifiers. Without a test, a homoglyph account can appear identical to a legitimate clinician.

**Secure Implementation Pattern:**
```python
# backend/tests/test_homoglyphs.py
import pytest

NAME_PAIRS = [("Admin Smith", "Аdmin Smith"),     # Cyrillic A
              ("Paul Moore", "Pаul Moore")]       # Cyrillic a

@pytest.mark.asyncio
@pytest.mark.parametrize("regular,lookalike", NAME_PAIRS)
async def test_lookalike_name_flagged(client, admin_headers, regular, lookalike):
    ok = await client.post("/api/staff", headers=admin_headers,
                           json={"full_name": regular, "email": "a@acme.test", "role": "nurse"})
    fake = await client.post("/api/staff", headers=admin_headers,
                             json={"full_name": lookalike, "email": "b@acme.test", "role": "nurse"})
    assert ok.status_code == 201
    assert fake.status_code == 422 or fake.json().get("display_warning") is True

@pytest.mark.asyncio
async def test_lookalike_bed_code_rejected(client, admin_headers, ward_id):
    r = await client.post(f"/api/wards/{ward_id}/beds", headers=admin_headers,
                          json={"code": "BED-01̵"})          # combining mark
    assert r.status_code == 422
```
```tsx
// frontend/src/components/__tests__/UserBadge.test.tsx
import { render } from "@testing-library/react";
import { it, expect } from "vitest";
import { UserBadge } from "../UserBadge";
it("distinguishes IDN email", () => {
  const a = render(<UserBadge name="Nurse" email="nurse@acme.test" />).container.textContent;
  const b = render(<UserBadge name="Nurse" email="nurse@аcme.test" />).container.textContent;
  expect(a).not.toEqual(b);
  expect(b).toContain("xn--");
});
```

**Implementation Guidance:**
- Identify views showing sensitive names/identifiers: staff management, alarm acknowledgement history, observation authors, device maintenance logs, reports, ward/bed labels.
- Submit data once with regular characters and once with homoglyphs (Cyrillic/Greek look-alikes, combining marks, full-width digits) via the API.
- Verify the outputs differ visibly (warning badge, Punycode domain) or the input is rejected; identical rendering fails the test.
- Include a manual check of generated reports (PDF/CSV) for the same pairs.
- Reference: SD Elements guidance for T1039.

**Success Criteria:**
- [ ] Backend and vitest homoglyph tests pass.
- [ ] Manual review documented for staff list, audit history and report outputs.

**Status:** Applied
