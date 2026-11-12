---
name: t219-avoid-transmitting-confidential-data-through-url-p
description: Keeps patient identifiers (names, MRNs, birth dates), observation text, search terms, passwords and tokens out of ACME Clinical URL query strings and SPA routes, using opaque UUIDs in paths and POST JSON bodies for searches, with server-side rejection of confidential query parameters.
---

# T219: Avoid transmitting confidential data through URL parameters

**Category:** CODE_FIX
**SD Elements:** [T219](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T219/)
**Priority:** 6/10 · **Phase:** development

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Search and filters are typically implemented as `GET /api/patients?name=John%20Doe&mrn=...` and mirrored in the SPA URL (`/patients?search=...`). These values end up in browser history, Vercel access logs, CSP reports, Referer headers and analytics, leaking PHI.

**Secure Implementation Pattern:**
```python
# backend/app/routers/patients.py
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()
FORBIDDEN_QS = {"name", "mrn", "dob", "search", "q", "note", "password", "token", "email"}

def reject_confidential_query(request: Request):
    bad = FORBIDDEN_QS & set(request.query_params)
    if bad:
        raise HTTPException(400, "Confidential parameters must be sent in the request body")

class PatientSearch(BaseModel):
    text: str = Field(default="", max_length=100)
    ward_id: UUID | None = None
    alarm_state: str | None = Field(default=None, pattern="^(active|acknowledged|none)$")

@router.post("/api/patients/search", dependencies=[Depends(reject_confidential_query)])
async def search(body: PatientSearch, user=Depends(current_user)): ...

@router.get("/api/patients/{patient_id}")  # opaque UUID, not MRN/name
async def get_patient(patient_id: UUID, user=Depends(current_user)): ...
```
```typescript
// frontend/src/services/patients.ts
export const searchPatients = (text: string, wardId?: string) =>
  api<Patient[]>("/api/patients/search", { method: "POST", body: JSON.stringify({ text, ward_id: wardId }) });
```

**Implementation Guidance:**
- Use opaque UUIDs (Supabase `gen_random_uuid()`) in API paths and SPA routes (`/patients/:id`); never MRN, name or bed+name.
- Send search text and filters with identifying content in POST JSON bodies; keep search state in React state, not in the URL. Non-identifying filters (ward UUID, alarm state) may be in the URL if needed for UX.
- Apply `reject_confidential_query` as a router-level dependency in `backend/app/routers/*.py` so clients cannot regress.
- Supabase Auth: password recovery tokens arrive in the URL fragment/code by design; call `supabase.auth.exchangeCodeForSession`/handle `PASSWORD_RECOVERY`, then remove them with `history.replaceState` immediately. Set `Referrer-Policy: strict-origin-when-cross-origin` (or `no-referrer`) in `frontend/vercel.json`.
- Supabase Storage signed URLs contain a token: keep TTL short (e.g. 60 s), never log them, and open them via `openSafely` (T512).
- Configure logging in `backend/app/core/logging.py` to log route templates (`/api/patients/{patient_id}`), not raw query strings.
- Reference: SD Elements guidance for T219.

**Success Criteria:**
- [ ] No API endpoint accepts names, MRNs, observation text, emails or passwords as query parameters (400 returned); a pytest covers this.
- [ ] SPA routes and history contain only UUIDs; after password recovery the URL no longer contains tokens.
- [ ] `Referrer-Policy` header is present on the frontend.

**Status:** Applied
