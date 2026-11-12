---
name: t162-validate-pathname-before-retrieving-local-resource
description: Ensures ACME Clinical never builds local paths or Supabase Storage object keys from user input; file references are resolved by database ID to server-generated keys and any local resource (report templates) is canonicalized and confined to an allow-listed directory.
---

# T162: Validate pathname before retrieving local resources

**Category:** CODE_FIX
**SD Elements:** [T162](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T162/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: threshold settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Endpoints such as `GET /files?path=patients/7/scan.png` or `GET /reports/template?name=ward.html` that pass the user string to Storage or `open()`. `../` sequences or other patients' prefixes allow reading other patients' files or server files.

**Secure Implementation Pattern:**
```python
# backend/app/routers/files.py
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import current_user, can_access_patient

router = APIRouter()

@router.get("/files/{file_id}/url")
async def signed_url(file_id: UUID, user=Depends(current_user), db=Depends(get_db)):
    meta = await db.get_file(file_id)                 # row: bucket, object_key, patient_id
    if not meta or not await can_access_patient(user, meta.patient_id):
        raise HTTPException(404)
    res = db.storage.from_(meta.bucket).create_signed_url(meta.object_key, 60)
    return {"url": res["signedURL"], "expires_in": 60}

# backend/app/services/reports.py  — local templates
from pathlib import Path
TEMPLATE_DIR = (Path(__file__).parent.parent / "report_templates").resolve()
ALLOWED_TEMPLATES = {"ward_summary", "patient_vitals", "alarm_log"}

def template_path(name: str) -> Path:
    if name not in ALLOWED_TEMPLATES:
        raise ValueError("unknown template")
    p = (TEMPLATE_DIR / f"{name}.html").resolve()
    if not p.is_relative_to(TEMPLATE_DIR):
        raise ValueError("path escape")
    return p
```

**Implementation Guidance:**
- Storage: clients reference files only by UUID; the backend looks up `bucket` + `object_key` (server-generated, see T2167) and checks patient/ward authorization before issuing a short-lived signed URL. Never accept a raw object path from the client.
- Local resources (report templates, fonts, logos): select from an allow-list (enum), resolve with `Path.resolve()` and verify `is_relative_to` the package directory.
- Do not read from the shared system temp directory except via private `tempfile` directories created by the app (T572).
- Frontend: no `src`/`href` built from user-entered paths; use returned signed URLs.
- Reference: SD Elements guidance for T162.

**Success Criteria:**
- [ ] No endpoint takes a file path or object key parameter; only UUIDs/enums.
- [ ] `template_path` rejects names outside the allow-list and traversal attempts (unit test).
- [ ] T297 traversal test passes.

**Status:** Pending
