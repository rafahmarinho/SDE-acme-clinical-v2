---
name: t177-allow-users-to-review-and-update-their-personal-in
description: Implement an authenticated ACME Clinical profile screen and /me API where staff review and correct all their personal data, with re-authentication for edits, validated input, confirmed email changes and non-personal immutable identifiers.
---

# T177: Allow users to review and update their personal information

**Category:** CODE_FIX
**SD Elements:** [T177](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T177/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A developer will build a profile page that reads from `profiles` with the anon key and lets users PATCH any column, including `role`, or only shows a subset of fields. Edits happen without re-authentication, email changes are applied directly, and staff identifiers may be derived from personal data (e.g. email prefix) making them non-editable.

**Secure Implementation Pattern:**
```python
# backend/app/routers/profile.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr, EmailStr
from app.core.security import current_user, recently_authenticated

router = APIRouter(prefix="/me")

class ProfileOut(BaseModel):
    id: str               # random UUID, never derived from personal data
    full_name: str
    email: EmailStr
    phone: str | None
    job_title: str | None
    role: str             # read-only here; managed by administrators

class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120, pattern=r"^[^\<\>]*$")
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9 ()-]{7,20}$")
    job_title: str | None = Field(default=None, max_length=80)
    current_password: SecretStr
    model_config = {"extra": "forbid"}   # blocks role/id tampering

@router.get("", response_model=ProfileOut)
async def get_me(user=Depends(current_user)):
    return await load_profile(user.id)

@router.patch("", response_model=ProfileOut)
async def update_me(body: ProfileUpdate, user=Depends(current_user)):
    if not await recently_authenticated(user, body.current_password):
        raise HTTPException(401, "Please confirm your password")
    return await save_profile(user.id, body.model_dump(exclude={"current_password"}))
```

**Implementation Guidance:**
- Add `GET/PATCH /me` and `POST /me/email` in `backend/app/routers/profile.py`; use `supabase.auth.update_user({"email": ...})` so the new address must be confirmed before it becomes the login ID.
- RLS on `profiles` in `supabase/migrations/0001_schema.sql`: `using (id = auth.uid())` for select/update and a column restriction/trigger preventing users from changing `role`.
- Treat profile view/edit as high risk: require password on update (or re-auth if the session is older than 5 minutes).
- Profile screen in `frontend/src/screens/` lists every staff personal field from the data classification, with loading and error states per the PRD.
- Provide a "Report a privacy concern" link that creates a record in `privacy_requests` for administrators to track inquiries and resolutions.
- Reference: SD Elements guidance for T177.

**Success Criteria:**
- [ ] Staff can view and edit all their personal fields; `role` and `id` cannot be changed via `/me`.
- [ ] Updates without a valid current password return 401; invalid formats return 422.
- [ ] Email change only takes effect after confirmation.
- [ ] T238 tests pass.

**Status:** Applied
