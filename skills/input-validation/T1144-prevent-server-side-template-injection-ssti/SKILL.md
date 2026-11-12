---
name: t1144-prevent-server-side-template-injection-ssti
description: Prevent server-side template injection in ACME Clinical's Python report generation (CSV/summary reports, notification text) by never compiling user-controlled strings as templates, using fixed templates with autoescaping and passing user data only as context values.
---

# T1144: Prevent Server-Side Template Injection (SSTI)

**Category:** CODE_FIX
**SD Elements:** [T1144](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T1144/)
**Priority:** 8/10 · **Phase:** development

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: frontend. Generation of readings, alarms and reports must be done in Python. The)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
Python-generated reports invite "customisable" report titles, headers or alarm message formats built with `jinja2.Template(user_string).render(...)` or `str.format(**obj)` on text that came from settings, observations or ward names. Compiling user-controlled text as a template lets an attacker evaluate expressions (`{{ cycler.__init__.__globals__ }}`) or read object attributes (`{0.__class__}`) on the server, i.e. remote code execution or secret disclosure inside the Vercel function.

**Secure Implementation Pattern:**
```python
# backend/app/services/reports.py
from jinja2 import select_autoescape
from jinja2.sandbox import ImmutableSandboxedEnvironment

# Templates are code: fixed strings shipped with the backend, never loaded from DB/requests.
_ENV = ImmutableSandboxedEnvironment(autoescape=select_autoescape(default=True),
                                     trim_blocks=True, lstrip_blocks=True)
_TEMPLATES = {
    "ward_activity_title": _ENV.from_string("Ward activity - {{ ward_name }} ({{ start }} to {{ end }})"),
}

def render_title(kind: str, *, ward_name: str, start: str, end: str) -> str:
    tpl = _TEMPLATES[kind]                       # KeyError -> 400 upstream; no dynamic lookup
    return tpl.render(ward_name=ward_name, start=start, end=end)   # user data only as values

# Never: Template(request_text).render(...), request_text.format(**row), eval/f-string building
def alarm_message(label: str, value: int) -> str:
    return "{label}: {value}".format(label=label, value=int(value))  # constant format string
```

**Implementation Guidance:**
- Inventory every place text is composed in `backend/app/services/reports.py`, `backend/app/services/alarms.py` and `backend/app/routers/reports.py`; format strings must be literals in code, never values read from `security_settings`, observations, ward names or query parameters.
- If Jinja2 (or any engine) is introduced, use `ImmutableSandboxedEnvironment` with autoescape, keep templates as constants or package files, and never call `from_string()` on request or database data.
- Do not use `str.format`/`format_map` with a user-controlled format string or with whole objects (`format(**row)`); pass explicit scalar arguments.
- Keep free-text fields validated by the shared Pydantic types (`backend/app/schemas/__init__.py`, `backend/app/core/validation.py` `clean_text`) so control characters and template delimiters in names are bounded; validation is defence in depth, not the primary control.
- Run the backend as the unprivileged Vercel function with no writable code path (see T4595 for platform hardening).
- Reference: SD Elements guidance for T1144.

**Success Criteria:**
- [ ] `grep -rn "from_string\|Template(\|\.format(\*\*\|format_map\|eval(" backend/app` shows no call on data originating from requests or the database.
- [ ] Test in `backend/tests/test_input_validation.py`: a ward/observation/report title value of `{{7*7}}` and `{0.__class__}` is rendered literally (no `49`, no class name) in report output.
- [ ] Any template engine in use is the sandboxed environment with autoescape enabled.

**Status:** Applied
