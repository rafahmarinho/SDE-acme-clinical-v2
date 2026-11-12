---
name: t519-test-that-input-validation-is-done-on-all-forms-of
description: Test recipe that inventories every ACME Clinical input (search, filters, observations, limits, staff, profile, simulation, uploads), records its acceptance criteria and tests each with unacceptable values.
---

# T519: Test that input validation is done on all forms of input

**Category:** CODE_FIX
**SD Elements:** [T519](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T519/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
The PRD lists many input surfaces (login, recovery, profile, settings, search, filters, observations, simulation). Teams typically test the main forms and forget query params, path ids, headers and upload metadata, leaving some inputs unvalidated.

**Secure Implementation Pattern:**
```python
# backend/tests/test_all_inputs.py
# Driven by the OpenAPI schema so new inputs are covered automatically.
import pytest
from app.main import app

BAD = {"string": ["", "A" * 10_000, "\x00", "‮"], "integer": [-1, 10**12, "x"],
       "number": [float("1e308"), "nan"], "boolean": ["maybe"], "uuid": ["../1", "1 OR 1=1"]}

def inputs():
    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            for p in op.get("parameters", []):
                s = p["schema"]; kind = "uuid" if s.get("format") == "uuid" else s.get("type")
                for v in BAD.get(kind, []):
                    yield method, path, p["name"], p["in"], v

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,name,where,value", list(inputs()))
async def test_param_rejected(client, admin_headers, method, path, name, where, value):
    url = path.replace("{" + name + "}", str(value)) if where == "path" else path
    params = {name: value} if where == "query" else None
    r = await client.request(method.upper(), url, params=params, headers=admin_headers)
    assert r.status_code in (400, 404, 422) and r.status_code != 500
```

**Implementation Guidance:**
- Build an input inventory (e.g. a table in `backend/tests/INPUTS` fixture or derived from `/openapi.json`) covering body fields, query/path params, headers, cookies, upload filename/MIME/size, Realtime messages.
- For each item record the acceptance criteria: type, allowed characters, length/size, range, enum.
- Test each with unacceptable values (empty, oversized, wrong type, control/bidi characters, out-of-range numbers); add body-field cases per model with Hypothesis or explicit lists.
- Add frontend tests (vitest) for client-side form validation to keep rules aligned.
- Reference: SD Elements guidance for T519.

**Success Criteria:**
- [ ] An input inventory exists and each entry has documented acceptance criteria.
- [ ] Schema-driven tests cover 100% of OpenAPI parameters and request models; none returns 500 or accepts invalid data.

**Status:** Pending
