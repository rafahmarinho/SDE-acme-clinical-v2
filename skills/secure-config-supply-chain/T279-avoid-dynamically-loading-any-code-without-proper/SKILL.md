---
name: t279-avoid-dynamically-loading-any-code-without-proper
description: Prevent ACME Clinical from loading code at runtime from untrusted or unverified locations - no eval/exec or plugin loading in the FastAPI backend, simulation scenarios as data not code, and only same-origin, build-time bundled chunks in the React SPA.
---

# T279: Avoid dynamically loading any code without proper security considerations

**Category:** CODE_FIX
**SD Elements:** [T279](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T279/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "Prepare dados de demonstração com doze pacientes e dez monitores. Inclua uma área para"
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: Prepare demo data with twelve patients and ten monitors. Include an area to choose scenarios, advance the simulation, view events and reset the data. The results)
> Source: specs/PRD.md, lines 41-43

**What the spec implies (naive approach):**
A flexible "choose scenarios" feature tempts developers to load scenario modules by name (`importlib.import_module(f"scenarios.{name}")`), `eval` scenario formulas, or let the 3D view pull scripts from a CDN at runtime. A tampered name, file in Storage or CDN response then becomes code execution on the API or in clinicians' browsers.

**Secure Implementation Pattern:**
```python
# backend/app/services/simulation.py - scenarios are a closed enum of data, never imported by name
class Scenario(StrEnum):
    normal = "normal"
    low_spo2 = "low_spo2"
    low_battery = "low_battery"
    sensor_fault = "sensor_fault"
    connection_loss = "connection_loss"

SCENARIO_PROFILES: Final[Mapping[Scenario, ScenarioProfile]] = MappingProxyType({...})

def apply(scenario: Scenario, state: MonitorState) -> MonitorState:
    return SCENARIO_PROFILES[scenario].step(state)   # no eval/exec/importlib
```
```ts
// frontend/src/App.tsx - lazy chunks are build-time, same-origin, covered by CSP script-src 'self'
const Simulation = lazy(() => import("./screens/Simulation"));   // static specifier only
```

**Implementation Guidance:**
- Backend: no `eval`, `exec`, `compile`, `pickle.loads`, `importlib.import_module` with request data, or `__import__` anywhere in `backend/app/`; scenarios in `backend/app/services/simulation.py` and routers in `backend/app/routers/simulation.py` accept only the `Scenario` enum via Pydantic.
- Never execute or import files from Supabase Storage (`clinical-files` bucket) or `/tmp`; uploaded files are data only (`backend/app/services/files.py`).
- Frontend: only static `import()` specifiers resolved by Vite at build time; no runtime `<script>` injection, `new Function`, or third-party CDN scripts; CSP `script-src 'self'` in `frontend/vercel.json` enforces it. If a 3D library is used, bundle it from npm via `pnpm-lock.yaml` (integrity hashes) rather than loading it from a CDN.
- Dependencies are installed from locked, integrity-checked registries only (`pnpm install --frozen-lockfile`, pinned `requirements.txt`).
- Reference: SD Elements guidance for T279.

**Success Criteria:**
- [ ] `backend/tests/test_secure_config.py::test_t305_no_dynamic_imports_or_exec_in_backend` and `test_t305_no_eval_or_remote_code_in_frontend` pass.
- [ ] `test_t305_csp_restricts_scripts_to_self` passes.
- [ ] Pytest: `POST /v1/simulation/scenario` with `"scenario": "__import__('os')"` or an unknown name returns 422.

**Status:** Pending
