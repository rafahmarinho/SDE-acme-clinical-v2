---
name: t569-prevent-parameter-tampering-in-web-services
description: Prevents parameter tampering on the ACME Clinical FastAPI web service by defining strongly typed Pydantic/OpenAPI request schemas (enums, ranges, formats, forbidden extra fields) in place of the WSDL constraints the countermeasure describes.
---

# T569: Prevent parameter tampering in web services

**Category:** CODE_FIX
**SD Elements:** [T569](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T569/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "O sistema médico vai se chamar ACME Clinical. Use Python com FastAPI e Pydantic no backend e"
> (EN: "The medical system will be called ACME Clinical. Use Python with FastAPI and Pydantic in the backend and")
> Source: specs/PRD.md, line 17

**What the spec implies (naive approach):**
The API is a JSON/REST service, not SOAP, so there is no WSDL. A developer may accept `dict` bodies or loosely typed `str` fields (e.g. `role: str`, `scenario: str`, `threshold: float`), letting clients submit unexpected roles, negative or absurd vital-sign limits, or extra fields such as `acknowledged_by`. The OpenAPI schema FastAPI generates from Pydantic models is the equivalent of the WSDL and must be strict.

**Secure Implementation Pattern:**
```python
# backend/app/schemas/common.py (pattern)
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

class Scenario(str, Enum):
    normal = "normal"; low_spo2 = "low_spo2"; low_battery = "low_battery"
    sensor_fault = "sensor_fault"; connection_loss = "connection_loss"

class Role(str, Enum):
    nurse = "nurse"; physician = "physician"
    biomed_tech = "biomedical_technician"; admin = "administrator"

class ApplyScenario(StrictModel):
    monitor_id: UUID
    scenario: Scenario
    duration_s: int = Field(ge=1, le=3600)

class AckAlarm(StrictModel):
    alarm_id: UUID
    note: str | None = Field(default=None, max_length=500)
```

**Implementation Guidance:**
- WSDL is not used by this stack; apply the same intent to FastAPI request models and the generated OpenAPI document (`/openapi.json`).
- Define a shared `StrictModel` base (`extra="forbid"`, `strict=True`) and inherit every request body from it in `backend/app/routers/*.py`.
- Use strong types only: `UUID` for ids, `bool`, bounded `int`/`float` (`Field(ge=, le=)`), `Enum`/`Literal` for scenarios, roles, alarm states, device states; `constr`/`max_length` for text.
- Type query parameters with `Annotated[..., Query(...)]` constraints too, not only bodies.
- Never accept server-owned fields (user id, role, timestamps, `acknowledged_by`) from the client; derive them from the authenticated session.
- Reference: SD Elements guidance for T569.

**Success Criteria:**
- [ ] Every request model in the OpenAPI schema has `additionalProperties: false` and no untyped (`{}`) properties.
- [ ] Enumerated fields (role, scenario, alarm state) appear as `enum` in `/openapi.json`.
- [ ] `backend/tests/test_schema_strictness.py` asserts unknown fields and out-of-enum values return 422.

**Status:** Applied
