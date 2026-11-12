---
name: t214-protect-confidential-files-on-operating-system-or
description: Protect confidential files handled by ACME Clinical - patient attachments in the private Supabase Storage bucket and temporary report/CSV files on the Vercel function filesystem - with least-privilege access, owner-only permissions, storage outside any web root and validation of permissions before use.
---

# T214: Protect confidential files on operating system or server

**Category:** CODE_FIX
**SD Elements:** [T214](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T214/)
**Priority:** 9/10 · **Phase:** requirements

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
"Files" with Supabase is often done with a public bucket and permanent public URLs, and reports are written to `/tmp/report.csv` with default permissions and a predictable name. Anyone who learns the URL or shares the function sandbox can read patient documents or exported data.

**Secure Implementation Pattern:**
```python
# backend/app/services/reports.py - private, owner-only temp files; extend the existing
# symlink/is_dir check with an ownership + permission check before use
def _ensure_root() -> Path:
    TMP_ROOT.mkdir(mode=0o700, exist_ok=True)
    st = os.lstat(TMP_ROOT)
    if (stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode)
            or (hasattr(os, "getuid") and st.st_uid != os.getuid()) or stat.S_IMODE(st.st_mode) & 0o077):
        raise PermissionError("report temp root has unsafe type, ownership or permissions")
    return TMP_ROOT

def create_exclusive(dirpath: str, name: str) -> IO[bytes]:
    fd = os.open(os.path.join(dirpath, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY, 0o600)
    return os.fdopen(fd, "wb")
```
```sql
-- supabase/migrations/0002_roles_rls.sql - private bucket, no browser policies
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('clinical-files', 'clinical-files', false, 5242880, array['application/pdf', 'image/png', 'image/jpeg'])
on conflict (id) do update set public = false;
```

**Implementation Guidance:**
- Attachments: keep the `clinical-files` bucket private (`public = false`) with no `storage.objects` policies for `anon`/`authenticated` (`supabase/migrations/0002_roles_rls.sql`); only the API uploads with the service key and issues short-lived signed URLs after an authorization check (`backend/app/routers/files.py` `GET /v1/files/{attachment_id}/url`).
- Object paths are random and server-generated (`new_object_path`, `safe_object_path` in `backend/app/services/files.py`), outside any web root; the original filename is display-only metadata.
- Before using a stored file, verify bucket privacy at startup or in a health check (Storage API `GET /bucket/clinical-files` -> `public == false`), failing closed and alerting admins if it was widened.
- Temporary report files (`backend/app/services/reports.py`): directory `0700`, files `0600`, created with `O_EXCL | O_NOFOLLOW`, ownership/permission checked before writing, removed after streaming (`private_workdir`, `sweep_expired`).
- Never write confidential files into `frontend/public/` or the backend source tree; never log file contents or signed URLs (`backend/app/core/logging.py` redaction).
- Reference: SD Elements guidance for T214.

**Success Criteria:**
- [ ] `backend/tests/test_files.py`: the bucket migration declares `public = false` and no browser-role storage policies exist.
- [ ] Pytest: a report workspace pre-created with mode `0777` or as a symlink is rejected; created files have mode `0600`.
- [ ] Pytest: signed URLs are issued only to authorized roles and expire (<= 60 s); a direct public Storage URL for an object returns 400/404.
- [ ] Temporary files are gone after the CSV export response completes.

**Status:** Applied
