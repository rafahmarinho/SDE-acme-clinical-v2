---
name: t31-validate-all-forms-of-input
description: Validates every input to ACME Clinical (search, filters, observations, alarm limit settings, staff management, simulation controls, environment variables, Realtime payloads) with allow-list Pydantic types, ranges and lengths, and logs rejections.
---

# T31: Validate all forms of input

**Category:** CODE_FIX
**SD Elements:** [T31](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T31/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you may create something very visual in 3D if")
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
The limits settings screen will likely post raw numbers for heart rate, SpO2, respiration and blood pressure thresholds, and staff management will accept names, emails and roles. A naive implementation accepts any float (negative, NaN, low > high) and any string, which can disable alarms for patients or store injection payloads.

**Secure Implementation Pattern:**
```python
# backend/app/schemas/limits.py
from typing import Annotated
from pydantic import Field, EmailStr, model_validator
from app.schemas.common import StrictModel, Role

HR = Annotated[int, Field(ge=20, le=250)]
SPO2 = Annotated[int, Field(ge=50, le=100)]
RR = Annotated[int, Field(ge=4, le=60)]
SYS = Annotated[int, Field(ge=50, le=260)]

class AlarmLimits(StrictModel):
    hr_low: HR; hr_high: HR
    spo2_low: SPO2
    rr_low: RR; rr_high: RR
    sys_low: SYS; sys_high: SYS

    @model_validator(mode="after")
    def consistent(self):
        if self.hr_low >= self.hr_high or self.rr_low >= self.rr_high or self.sys_low >= self.sys_high:
            raise ValueError("low limit must be below high limit")
        return self

class StaffCreate(StrictModel):
    full_name: str = Field(min_length=1, max_length=120, pattern=r"^[\p{L} .'-]+$")
    email: EmailStr
    role: Role
```

**Implementation Guidance:**
- Model every body, query and path parameter in `backend/app/routers/*.py` with Pydantic; check data type, range, structure and cross-field consistency (low < high limits, bed belongs to ward).
- Prefer allow-lists: enums for roles, scenarios, alarm states, sort fields; regex patterns for names/codes. Use block-lists only where allow-lists are impossible (free-text observations: length cap, no control characters).
- Note: `\p{L}` works with Pydantic v2's default Rust regex engine; it is not supported if `regex_engine="python-re"` is configured, so keep the default or use a custom validator.
- Validate non-HTTP inputs too: env vars in `backend/app/core/config.py` via `pydantic-settings`, simulation scenario files, Supabase Realtime payloads consumed in `frontend/src/services`.
- Encode output (React escaping, JSON responses) and log validation failures through a `RequestValidationError` handler in `backend/app/core/errors.py`.
- Reference: SD Elements guidance for T31.

**Success Criteria:**
- [ ] Every router parameter is typed with a bounded Pydantic/`Annotated` type; no `dict`/`Any` bodies.
- [ ] Tests: `hr_low=300`, `spo2_low=-1`, `hr_low > hr_high`, unknown role all return 422.
- [ ] Validation failures are logged with timestamp, route and client IP (no sensitive values).

**Status:** Pending
