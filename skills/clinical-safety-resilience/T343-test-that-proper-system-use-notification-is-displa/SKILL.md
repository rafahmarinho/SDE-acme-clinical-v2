---
name: t343-test-that-proper-system-use-notification-is-displa
description: Test that ACME Clinical shows required system-use and critical-action notices (audit, responsibility, alarm acknowledgement does not end the condition) for limit changes, alarm acknowledgement, data reset, role changes and break-glass, and that they require explicit acknowledgement.
---

# T343: Test that proper system use notification is displayed or sent for critical features

**Category:** CODE_FIX
**SD Elements:** [T343](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T343/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "acompanhar manutenção. Reconhecer um alarme não encerra uma condição que ainda está"
> (EN: "...track maintenance. Acknowledging an alarm does not end a condition that is still")
> Source: specs/PRD.md, line 35

**What the spec implies (naive approach):**
Warnings get removed or bypassed during UI refactors, and API clients can skip them entirely. Without tests, there is no proof that each critical feature still warns and requires explicit consent.

**Secure Implementation Pattern:**
```ts
// frontend/src/components/CriticalActionDialog.test.tsx (vitest + testing-library)
const CRITICAL = [
  { open: openAckDialog,       must: [/does not resolve the condition/i] },
  { open: openThresholdDialog, must: [/old value/i, /new value/i] },
  { open: openResetDialog,     must: [/type reset/i] },
  { open: openRoleDialog,      must: [/role change/i] },
  { open: openBreakGlass,      must: [/full responsibility/i] },
];

it.each(CRITICAL)("shows notice and requires explicit consent", async ({ open, must }) => {
  await open();
  expect(screen.getByText(/recorded in the audit log/i)).toBeVisible();
  for (const m of must) expect(screen.getByText(m)).toBeVisible();
  const confirm = screen.getByRole("button", { name: /confirm/i });
  expect(confirm).toBeDisabled();
  await userEvent.click(screen.getByLabelText(/i understand/i));
  expect(confirm).toBeEnabled();
});
```
```python
# backend/tests/test_critical_ack_required.py
@pytest.mark.parametrize("method,path,role", [
    ("POST", "/api/alarms/{aid}/ack", "nurse"), ("PUT", "/api/thresholds/{tid}", "physician"),
    ("POST", "/api/simulation/reset", "administrator")])
async def test_api_requires_acknowledgement(client_as, ids, method, path, role):
    r = await client_as(role, auth_age_minutes=0).request(method, path.format(**ids), json={})
    assert r.status_code == 422
```

**Implementation Guidance:**
- Enumerate critical features (list from T342) and keep it as the parameter set for both frontend and backend tests.
- Check message content: important service, audited/recorded, user responsible for misuse; consent to monitoring at login. Government-system clause: not applicable (fictional demo).
- Verify the notice stays until explicit action (no auto-dismiss, Escape does not confirm).
- Verify the login system-use notice is shown before access to any data (Playwright).
- Reference: SD Elements guidance for T343.

**Success Criteria:**
- [ ] Vitest suite passes for every critical feature.
- [ ] Backend returns 422 when acknowledgement fields are missing.
- [ ] Playwright confirms login notice precedes data access.

**Status:** Applied
