---
name: t1148-validate-json-files
description: Validates all JSON consumed by ACME Clinical (API request bodies, simulation scenario files, seed/config JSON, Realtime payloads) against schemas, and never builds JSON by string concatenation of user input.
---

# T1148: Validate JSON files

**Category:** CODE_FIX
**SD Elements:** [T1148](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1148/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: "choose scenarios, advance the simulation, view events and reset the data. The results")
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
Simulation scenarios, event payloads and Realtime messages are naturally JSON. A developer may load scenario definitions with `json.load` and use the dict directly, store arbitrary `jsonb` event details, or assemble JSON in the frontend with template strings, risking malformed structures and XSS when values are later rendered.

**Secure Implementation Pattern:**
```python
# backend/app/services/simulation.py
import json
from pathlib import Path
from typing import Literal
from pydantic import Field, TypeAdapter
from app.schemas.common import StrictModel

class ScenarioStep(StrictModel):
    at_s: int = Field(ge=0, le=86_400)
    metric: Literal["hr", "spo2", "rr", "sys", "dia", "battery", "signal"]
    value: float = Field(ge=0, le=300)

class ScenarioFile(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9_]{3,40}$")
    name: str = Field(max_length=80)
    steps: list[ScenarioStep] = Field(max_length=500)

_adapter = TypeAdapter(list[ScenarioFile])

def load_scenarios(path: Path) -> list[ScenarioFile]:
    raw = path.read_bytes()
    if len(raw) > 512_000:
        raise ValueError("scenario file too large")
    return _adapter.validate_json(raw)      # parse + validate in one step
```

**Implementation Guidance:**
- Treat Pydantic models as the JSON Schema: FastAPI validates request bodies; use `TypeAdapter.validate_json` for files and stored `jsonb`.
- Export schemas (`ScenarioFile.model_json_schema()`) for tests and frontend validation (e.g. zod/ajv in `frontend/src/lib`) of Realtime payloads before rendering.
- Constrain `jsonb` columns in `supabase/migrations/0001_schema.sql` with CHECKs (e.g. `jsonb_typeof(details) = 'object'`) and size limits.
- Never build JSON with string concatenation; use `json.dumps` / `JSONResponse` in Python and `JSON.stringify` in TypeScript.
- Reference: SD Elements guidance for T1148.

**Success Criteria:**
- [ ] All JSON inputs (bodies, scenario files, Realtime messages) pass through a schema validator before use.
- [ ] Unit tests: scenario files with unknown keys, wrong types or oversized arrays raise validation errors.
- [ ] No code builds JSON via f-strings or template literals.

**Status:** Applied
