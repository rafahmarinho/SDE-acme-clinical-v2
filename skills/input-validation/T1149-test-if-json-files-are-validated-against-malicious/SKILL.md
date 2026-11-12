---
name: t1149-test-if-json-files-are-validated-against-malicious
description: Test recipe submitting malformed and schema-violating JSON to ACME Clinical endpoints and scenario loaders to confirm each is rejected with a clear validation error.
---

# T1149: Test if JSON files are validated against malicious inputs

**Category:** CODE_FIX
**SD Elements:** [T1149](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1149/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: "choose scenarios, advance the simulation, view events and reset the data. The results")
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
Simulation and settings endpoints accept JSON. Without negative tests, malformed JSON, deeply nested objects, duplicate keys or type confusion may slip through or cause 500 errors.

**Secure Implementation Pattern:**
```python
# backend/tests/test_json_validation.py
import pytest

MALICIOUS = [
    b'{"monitor_id": "1", "scenario": "low_spo2"',                     # truncated
    b'{"monitor_id": 1, "scenario": ["low_spo2"]}',                     # type confusion
    b'{"monitor_id": "00000000-0000-0000-0000-000000000001", "scenario": "low_spo2", "__proto__": {"admin": true}}',
    b'{"a":' * 5000 + b'1' + b'}' * 5000,                               # deep nesting
    b'{"scenario": "low_spo2", "scenario": "reset_all"}',              # duplicate keys
]

@pytest.mark.asyncio
@pytest.mark.parametrize("raw", MALICIOUS)
async def test_simulation_rejects_bad_json(client, admin_headers, raw):
    r = await client.post("/api/simulation/scenario", content=raw,
                          headers={**admin_headers, "Content-Type": "application/json"})
    assert r.status_code in (400, 413, 422)

def test_scenario_file_schema(tmp_path):
    from app.services.simulation import load_scenarios
    p = tmp_path / "s.json"; p.write_text('[{"id":"X!","name":"n","steps":[]}]')
    with pytest.raises(Exception):
        load_scenarios(p)
```

**Implementation Guidance:**
- Locate each JSON input and its Pydantic schema (request models, `ScenarioFile`, Realtime payload types).
- Craft inputs that break the schema: short/long strings, wrong types, unknown keys, out-of-range numbers, nesting bombs, duplicate keys, invalid UTF-8.
- Submit them and assert an error response (422/400/413) with a generic message; the test fails if the input is accepted or the server crashes.
- Add vitest cases for frontend validation of Realtime payloads.
- Reference: SD Elements guidance for T1149.

**Success Criteria:**
- [ ] `backend/tests/test_json_validation.py` passes for every JSON-accepting endpoint.
- [ ] No malicious JSON produces a 500 or a persisted record.

**Status:** Pending
