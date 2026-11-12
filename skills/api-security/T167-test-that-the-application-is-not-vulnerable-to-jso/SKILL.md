---
name: t167-test-that-the-application-is-not-vulnerable-to-jso
description: Test that every ACME Clinical FastAPI JSON response uses Content-Type application/json and a top-level JSON object (lists wrapped as {"items": [...]}) so responses cannot be hijacked via script inclusion.
---

# T167: Test that the application is not vulnerable to JSON Hijacking

**Category:** CODE_FIX
**SD Elements:** [T167](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T167/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> "filtros, estados de carregamento e mensagens de erro."
> (EN: Include login, password recovery, profile, settings, search, filters, loading states and error messages.)
> Source: specs/PRD.md, lines 11-13

**What the spec implies (naive approach):**
Search and filter endpoints for patients, alarms and events would naturally be written as `response_model=list[PatientOut]`, returning a bare JSON array. A top-level array is the classic JSON-hijacking shape. Modern browsers and the Bearer-token design (a `<script src>` cannot attach the `Authorization` header) reduce the risk, but if a cookie-based session is ever added the arrays become exploitable, so the format should be safe by construction.

**Secure Implementation Pattern:**
```python
# backend/app/routers/alarms.py
class Page(BaseModel, Generic[T]):
    items: list[T]; total: int; next_cursor: str | None = None

@router.get("/alarms", response_model=Page[AlarmOut])        # never response_model=list[AlarmOut]
async def search_alarms(...): ...

# backend/tests/test_json_format.py
async def test_all_json_responses_are_objects(app, api, admin):
    for route in app.routes:
        if not isinstance(route, APIRoute) or "GET" not in route.methods or "{" in route.path:
            continue
        r = await api.get(route.path, headers=admin.auth_header)
        if r.status_code >= 400 and not r.content: continue
        assert r.headers["content-type"].startswith("application/json"), route.path
        assert r.text.lstrip()[:1] == "{", f"{route.path} returns a top-level array"

def test_no_route_declares_list_response(app):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.response_model is not None:
            assert get_origin(route.response_model) is not list, route.path
```

**Implementation Guidance:**
- Use a shared `Page[T]` envelope in `backend/app/routers/*` for every list, search and filter endpoint (patients, alarms, events, devices, maintenance, observations, staff, reports).
- Error handlers in `backend/app/core/errors.py` also return objects (`{"error": ..., "detail": ...}`) with `application/json`.
- Add `X-Content-Type-Options: nosniff` to all API responses (middleware in `backend/app/main.py`).
- Tests in `backend/tests/test_json_format.py` (static route check + runtime check of first non-whitespace character and MIME type). Manual check: DevTools Network tab filtered to Fetch/XHR, inspect the first character of each response.
- Reference: SD Elements guidance for T167.

**Success Criteria:**
- [ ] No route declares a list as its response model.
- [ ] Every JSON response starts with `{` and has `Content-Type: application/json`.
- [ ] `X-Content-Type-Options: nosniff` present on API responses.

**Status:** Applied
