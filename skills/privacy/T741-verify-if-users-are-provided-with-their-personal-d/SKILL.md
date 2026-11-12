---
name: t741-verify-if-users-are-provided-with-their-personal-d
description: Test recipe verifying ACME Clinical staff can securely obtain their personal data and processing information in machine-readable JSON, and that the export is scoped to the requester.
---

# T741: Verify if users are provided with their personal data and its processing information in an appropriate format

**Category:** CODE_FIX
**SD Elements:** [T741](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T741/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
The profile screen exists but there is usually no export or processing information page. If present, it may be reachable without re-authentication or return another user's data by changing an ID.

**Secure Implementation Pattern:**
```python
# backend/tests/test_data_export.py
import json, pytest

REQUIRED = {"purposes", "recipients", "retention", "source", "automated_decisions"}

@pytest.mark.asyncio
async def test_export_is_machine_readable_and_complete(client, nurse):
    r = await client.post("/me/export", headers=auth(nurse.token),
                          json={"current_password": nurse.password})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = json.loads(r.content)
    assert body["profile"]["email"] == nurse.email
    assert REQUIRED <= body["processing"].keys()

@pytest.mark.asyncio
async def test_export_requires_reauth_and_is_scoped(client, nurse, physician):
    assert (await client.post("/me/export", headers=auth(nurse.token), json={})).status_code in (401, 422)
    r = await client.post("/me/export", headers=auth(nurse.token),
                          json={"current_password": nurse.password})
    assert physician.email not in r.text
```

**Implementation Guidance:**
- Test the export from T740 (`backend/app/routers/profile.py`) and the profile screen button.
- Compare export contents against the staff categories listed in `docs/security/data-classification.md`; any missing category fails the test.
- Verify a page (the `/privacy` notice plus the profile "Your data" section) shows processing information.
- Reference: SD Elements guidance for T741.

**Success Criteria:**
- [ ] Export returns valid JSON covering all classified staff data categories.
- [ ] Processing metadata keys are present.
- [ ] Export without re-authentication is rejected; no cross-user data.
- [ ] Frontend test confirms the "Export my data" control exists on the profile screen.

**Status:** Applied
