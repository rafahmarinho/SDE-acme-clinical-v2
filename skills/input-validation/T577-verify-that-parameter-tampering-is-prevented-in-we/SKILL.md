---
name: t577-verify-that-parameter-tampering-is-prevented-in-we
description: Test recipe verifying that the ACME Clinical FastAPI OpenAPI/Pydantic schema (the REST equivalent of WSDL, which is not used) is strongly typed and rejects tampered parameters.
---

# T577: Verify that parameter tampering is prevented in web services

**Category:** CODE_FIX
**SD Elements:** [T577](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T577/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "O sistema médico vai se chamar ACME Clinical. Use Python com FastAPI e Pydantic no backend e"
> (EN: "The medical system will be called ACME Clinical. Use Python with FastAPI and Pydantic in the backend and")
> Source: specs/PRD.md, line 17

**What the spec implies (naive approach):**
No SOAP/WSDL exists; the contract is FastAPI's generated OpenAPI schema. Without a test, loose types (`Any`, `dict`, plain `str` for enumerations) silently creep into routers and allow clients to tamper with parameters such as roles, scenarios or alarm thresholds.

**Secure Implementation Pattern:**
```python
# backend/tests/test_openapi_strictness.py
from app.main import app

def walk(schema, defs, path=""):
    if "$ref" in schema:
        return
    t = schema.get("type")
    assert t or "enum" in schema or "anyOf" in schema or "allOf" in schema, f"untyped {path}"
    if t == "object":
        assert schema.get("additionalProperties") is False, f"loose object {path}"
        for k, v in schema.get("properties", {}).items():
            walk(v, defs, f"{path}.{k}")
    if t == "string" and "enum" not in schema and "format" not in schema:
        assert "maxLength" in schema, f"unbounded string {path}"
    if t in ("integer", "number"):
        assert "maximum" in schema and "minimum" in schema, f"unbounded number {path}"

def test_request_schemas_are_strict():
    spec = app.openapi()
    defs = spec["components"]["schemas"]
    for name, s in defs.items():
        if name.endswith(("In", "Create", "Update", "Request")):
            walk(s, defs, name)
```

**Implementation Guidance:**
- Adapt the WSDL checks to OpenAPI: each request schema must be typed, bounded and closed (`additionalProperties: false`).
- Run the schema walker above in CI against `app.openapi()`; adopt a naming convention for request models so the test can target them.
- Add dynamic tests: send wrong types (`"abc"` for an integer threshold), out-of-enum values (`role: "superuser"`), extra fields (`acknowledged_by`) and assert HTTP 422.
- Manual check: with an HTTP proxy, tamper with a captured request from the limits settings screen and confirm rejection.
- Reference: SD Elements guidance for T577.

**Success Criteria:**
- [ ] `test_openapi_strictness.py` passes with zero untyped, unbounded or open request schemas.
- [ ] Tampered requests (wrong type, unknown enum, extra field) return 422 for every write endpoint.

**Status:** Applied
