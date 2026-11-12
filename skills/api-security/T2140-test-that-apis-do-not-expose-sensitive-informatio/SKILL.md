---
name: t2140-test-that-apis-do-not-expose-sensitive-informatio
description: Tests verifying that every ACME Clinical FastAPI endpoint returns only the fields declared in explicit Pydantic response models, appropriate to the caller's role, with no internal, auth or excessive patient data in responses or errors.
---

# T2140: Test that APIs do not expose sensitive information

**Category:** CODE_FIX
**SD Elements:** [T2140](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2140/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

> "configurações de limites, relatórios e gestão da equipe"
> (EN: threshold settings, reports and team management)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
A quick FastAPI implementation returns rows straight from Supabase (`return res.data`) or `select *`, so the patient list ships full records (date of birth, medical record number, notes) when only name, bed and status are shown, and the staff endpoint leaks `auth.users` metadata, phone numbers or `last_sign_in_at`. Unhandled exceptions may return stack traces or SQL errors.

**Secure Implementation Pattern:**
```python
# backend/app/routers/patients.py
class PatientListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; display_name: str; ward_id: int; bed_label: str | None; status: str

class PatientListOut(BaseModel):
    items: list[PatientListItem]; total: int

@router.get("/patients", response_model=PatientListOut)
async def list_patients(sess=Depends(require_session), db=Depends(get_db)):
    rows = await db.fetch("select id, display_name, ward_id, bed_label, status from patients_v")  # explicit columns
    return {"items": rows, "total": len(rows)}

# backend/tests/test_api_exposure.py
EXPECTED = {
    "/patients": {"items", "total"},
    "/staff": {"items", "total"},
}
FORBIDDEN_KEYS = {"password", "encrypted_password", "raw_user_meta_data", "service_role",
                  "refresh_token", "phone", "ip", "stack", "traceback"}

def all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items(): yield k; yield from all_keys(v)
    elif isinstance(obj, list):
        for v in obj: yield from all_keys(v)

def test_every_route_declares_response_model(app):
    for r in app.routes:
        if isinstance(r, APIRoute) and r.status_code != 204:
            assert r.response_model is not None, f"{r.path} has no response_model"

async def test_no_forbidden_fields(api, admin):
    for path in ("/patients", "/patients/1", "/staff", "/alarms", "/devices", "/me", "/auth/sessions"):
        body = (await api.get(path, headers=admin.auth_header)).json()
        assert not FORBIDDEN_KEYS & set(all_keys(body)), path
```

**Implementation Guidance:**
- Every router in `backend/app/routers/*.py` declares `response_model=` with a dedicated `*Out` schema (never the DB/input model); FastAPI then filters undeclared fields. Select explicit columns in queries.
- Role-specific views: e.g. a biomedical technician sees devices and maintenance but not patient observations; use separate response models per role or return `403`.
- Keep error responses generic (`backend/app/core/errors.py`): `{ "error": "internal_error", "request_id": ... }`; never return exception text or SQL messages. Disable `/docs` and `/openapi.json` in production or protect them.
- Tests in `backend/tests/test_api_exposure.py`: route inventory (all routes have response models), forbidden-key scan per role, and a per-endpoint expected-field snapshot that must be updated deliberately when a field is added.
- Also check list sizes: list endpoints are paginated (`limit` capped, e.g. 100).
- Reference: SD Elements guidance for T2140.

**Success Criteria:**
- [ ] All non-204 routes have a `response_model`; test fails otherwise.
- [ ] No response contains auth secrets, internal metadata, or fields not displayed by the UI.
- [ ] Error responses contain no stack trace or SQL detail.
- [ ] Role-specific tests show each role receives only the fields it needs.

**Status:** Applied
