---
name: t179-allow-access-for-users-to-remove-their-personal-in
description: Provide a re-authenticated account removal flow for ACME Clinical staff that deletes their Supabase Auth user, profile and files and de-identifies clinical records they authored, plus an admin deactivation/erasure path in team management.
---

# T179: Allow access for users to remove their personal information from the system

**Category:** CODE_FIX
**SD Elements:** [T179](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T179/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: Include login, password recovery, profile, settings, search,)
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
A profile page and team management are specified, but no right to deletion. Developers typically omit removal, or let an admin hard-delete a row in `profiles` while the Supabase Auth user, avatar in Storage and the staff name embedded in observations and alarm acknowledgements remain. Personal data may also be written to logs that cannot be cleaned.

**Secure Implementation Pattern:**
```python
# backend/app/routers/profile.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, SecretStr
from app.core.security import current_user, verify_password_with_supabase
from app.db import service_client  # service role key, server-only

router = APIRouter(prefix="/me")

class DeleteRequest(BaseModel):
    current_password: SecretStr

@router.post("/delete", status_code=status.HTTP_202_ACCEPTED)
async def delete_my_account(body: DeleteRequest, user=Depends(current_user)):
    if not await verify_password_with_supabase(user.email, body.current_password.get_secret_value()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Re-authentication failed")
    sb = service_client()
    # keep clinical audit trail, but unlink identity
    sb.table("observations").update({"author_name": None}).eq("author_id", user.id).execute()
    sb.table("alarm_events").update({"acknowledged_by_name": None}).eq("acknowledged_by", user.id).execute()
    sb.storage.from_("avatars").remove([f"{user.id}/avatar.png"])
    sb.table("profiles").delete().eq("id", user.id).execute()
    sb.auth.admin.delete_user(user.id)          # revokes sessions too
    sb.table("deletion_log").insert({"subject_ref": user.pseudo_ref}).execute()
    return {"status": "deleted"}
```

**Implementation Guidance:**
- Add `POST /me/delete` in `backend/app/routers/profile.py`; require the current password (re-check via Supabase `sign_in_with_password`) or an emailed confirmation link.
- In `frontend/src/screens/` profile screen, add a "Delete account" section with an explanation that the service will not work without an account and that clinical audit records are retained de-identified per retention rules.
- For administrators, add "Deactivate" and "Erase" actions in team management (`backend/app/routers/staff.py`), restricted to the administrator role.
- Reference staff in clinical tables by `author_id` (UUID) and display names via join, so deletion leaves no copied names; never log names/emails (`backend/app/core/logging.py` redaction filter).
- Use the service role key only in the backend (`backend/app/db.py`).
- Reference: SD Elements guidance for T179.

**Success Criteria:**
- [ ] Staff can remove their account from the profile screen after re-entering their password.
- [ ] Removal deletes the auth user, profile row and Storage files, and nulls copied identifiers in clinical tables.
- [ ] Administrators can deactivate/erase staff; other roles get 403.
- [ ] Tests from T240 pass; log output contains no email/name for these operations.

**Status:** Pending
