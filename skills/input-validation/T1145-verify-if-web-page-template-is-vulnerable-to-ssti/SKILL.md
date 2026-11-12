---
name: t1145-verify-if-web-page-template-is-vulnerable-to-ssti
description: Test recipe ensuring ACME Clinical's Python report generation (and any Jinja2 templates) treats patient names, observations and report titles as data, not template code, so SSTI payloads are not evaluated.
---

# T1145: Verify if web page template is vulnerable to SSTI

**Category:** CODE_FIX
**SD Elements:** [T1145](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1145/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: "frontend. The generation of readings, alarms and reports must be done in Python. The")
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
Reports built in `backend/app/services/reports.py` will likely use Jinja2 (HTML/PDF) or f-strings. A developer may let users customize a report title or header and call `Template(user_title).render(...)` / `env.from_string(...)`, turning `{{'5'*5}}` or `{{cycler.__init__.__globals__.os.popen('id').read()}}` into code execution.

**Secure Implementation Pattern:**
```python
# backend/app/services/reports.py (control)
from jinja2 import PackageLoader, select_autoescape
from jinja2.sandbox import SandboxedEnvironment  # defense in depth only

env = SandboxedEnvironment(loader=PackageLoader("app", "templates"),
                           autoescape=select_autoescape(["html", "xml"]))

def render_patient_report(ctx: dict) -> str:
    # templates are fixed files; user values are only context variables
    return env.get_template("patient_report.html").render(**ctx)

# backend/tests/test_ssti.py
import pytest
SSTI = ["{{'5'*5}}", "{{7*7}}", "${7*7}", "{% raw %}{{x}}{% endraw %}",
        "{{cycler.__init__.__globals__.os.popen('id').read()}}"]

@pytest.mark.parametrize("p", SSTI)
def test_report_does_not_evaluate(p):
    html = render_patient_report({"patient_name": p, "title": p, "observations": [p]})
    assert "55555" not in html and "49" not in html and "uid=" not in html
    assert p.replace("'", "&#39;") in html or p in html
```

**Implementation Guidance:**
- Find every place user input reaches a template: report titles, patient names, observations, staff names in `backend/app/services/reports.py` and email-like notifications.
- Inject payloads (`{{'5'*5}}`, `{{7*7}}`, `${7*7}`, Jinja2 object-walk payloads) through the API (create observation, set report title) and download the report; output `55555`/`49` means failure.
- The control: templates loaded only from `backend/app/templates/` files; never `from_string`/`Template()` on user data; autoescape enabled; sandbox as defense in depth, not the primary control.
- If no template engine is used (pure ReportLab or CSV), document that and still run the payload test on the generated output.
- Reference: SD Elements guidance for T1145.

**Success Criteria:**
- [ ] `backend/tests/test_ssti.py` passes; payloads appear literally (escaped) in reports.
- [ ] Code search finds no `from_string(`, `Template(` or `render_template_string` applied to request data.

**Status:** Pending
