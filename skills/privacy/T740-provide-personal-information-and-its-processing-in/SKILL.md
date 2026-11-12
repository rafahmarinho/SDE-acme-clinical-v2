---
name: t740-provide-personal-information-and-its-processing-in
description: Implement an ACME Clinical self-service export where re-authenticated staff download all their personal data plus processing metadata (purposes, recipients, retention, source) as JSON.
---

# T740: Provide personal information and its processing information to users in an appropriate format

**Category:** CODE_FIX
**SD Elements:** [T740](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T740/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you can create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Reports and team management exist, but nothing lets a staff member obtain a copy of their own data. If an export is added, it is often an unauthenticated CSV link or includes other users' data, without processing metadata.

**Secure Implementation Pattern:**
```python
# backend/app/routers/profile.py
from datetime import datetime, timezone
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, SecretStr

class ExportRequest(BaseModel):
    current_password: SecretStr

@router.post("/export")
async def export_my_data(body: ExportRequest, user=Depends(current_user)):
    if not await recently_authenticated(user, body.current_password):
        raise HTTPException(401, "Please confirm your password")
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "subject_id": user.id,
        "profile": await load_profile(user.id),
        "consents": await list_consents(user.id),
        "observations_authored": await list_observation_ids(user.id),
        "alarm_acknowledgements": await list_acks(user.id),
        "processing": {
            "purposes": ["authentication", "clinical audit trail"],
            "recipients": ["Supabase (processor)", "Vercel (processor)"],
            "retention": await retention_summary(),
            "source": "Collected from you or your administrator",
            "automated_decisions": "None; alarms are threshold rules on patient vitals",
            "international_transfer": "Per Supabase/Vercel region configuration",
            "withheld": "Patient clinical content is part of the patient record and not included",
        },
    }
    await audit("data_export", actor=user.id)
    return JSONResponse(data, headers={"Content-Disposition": "attachment; filename=my-data.json",
                                       "Cache-Control": "no-store"})
```

**Implementation Guidance:**
- Add `POST /me/export` in `backend/app/routers/profile.py`; require password re-entry (identity proportionate to sensitivity).
- Query only rows owned by `user.id`; never include other staff or patient identities.
- Add an "Export my data" button on the profile screen (`frontend/src/screens/`) that downloads the JSON.
- Administrators may run the same export for a staff member on request (`backend/app/routers/staff.py`), audited.
- Reference: SD Elements guidance for T740.

**Success Criteria:**
- [ ] Export requires re-authentication and returns JSON with `Cache-Control: no-store`.
- [ ] Export includes profile, consents, activity references and processing metadata.
- [ ] Export contains no data from other users or patient identities.
- [ ] Each export is audit-logged without personal data in the log message.

**Status:** Pending
