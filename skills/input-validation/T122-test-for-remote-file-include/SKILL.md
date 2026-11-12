---
name: t122-test-for-remote-file-include
description: Test recipe verifying that SSI/include directives and remote file references submitted in ACME Clinical inputs are never evaluated by Vercel static hosting, the FastAPI backend or report generation.
---

# T122: Test for remote file include

**Category:** CODE_FIX
**SD Elements:** [T122](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T122/)
**Priority:** 10/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: "React with Vite and TypeScript in the frontend, deployed separately on Vercel. Use pnpm in the")
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
The app is served by Vercel (static SPA + Python functions), not IIS/Apache/Nginx, so classic SSI processing is not expected. The residual risk is in our own code: report templates that include files by user-provided name, or backend code that loads a template/scenario from a user-supplied path or URL. A test confirms neither SSI nor dynamic includes are honored.

**Secure Implementation Pattern:**
```python
# backend/tests/test_file_include.py
import pytest

SSI = ['<!--#include virtual="/etc/passwd" -->', '<!--#exec cmd="id" -->',
       '<!--#echo var="DOCUMENT_ROOT" -->', "{% include '/etc/passwd' %}",
       "http://attacker.example/x.txt", "../../app/core/config.py"]

@pytest.mark.asyncio
@pytest.mark.parametrize("p", SSI)
async def test_inputs_not_included(client, nurse_headers, patient_id, p):
    r = await client.post(f"/api/patients/{patient_id}/observations",
                          json={"text": p}, headers=nurse_headers)
    assert r.status_code in (201, 422)
    rep = await client.get(f"/api/reports/patients/{patient_id}", headers=nurse_headers)
    body = rep.text
    assert "root:x:" not in body and "uid=" not in body and "SUPABASE" not in body

@pytest.mark.asyncio
async def test_scenario_param_is_enum(client, admin_headers):
    r = await client.post("/api/simulation/scenario",
                          json={"monitor_id": "00000000-0000-0000-0000-000000000001",
                                "scenario": "http://attacker.example/s.json"}, headers=admin_headers)
    assert r.status_code == 422
```

**Implementation Guidance:**
- Identify pages/endpoints echoing user input: observations, notes, names, search, report output, headers/cookies.
- Submit SSI directives (`#include`, `#exec`, `#echo`), template include tags and remote/relative file references; verify the response shows them inert and no external or local file content is included.
- The control: Vercel does not process SSI; templates and scenario files are chosen from server-side allow-lists (enums), never by user path or URL; backend never fetches user URLs (see T1392).
- Repeat the check against the deployed frontend URL for the static `index.html`.
- Reference: SD Elements guidance for T122.

**Success Criteria:**
- [ ] `backend/tests/test_file_include.py` passes.
- [ ] Manual check on the Vercel deployments shows SSI directives rendered as text.

**Status:** Applied
