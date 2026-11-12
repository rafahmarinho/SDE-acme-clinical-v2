---
name: t2167-secure-file-storage
description: Stores ACME Clinical uploads in private Supabase Storage buckets under random server-generated object keys with storage RLS, validated display names, size and MIME limits, and access only through short-lived signed URLs, never in the public frontend bundle or a public bucket.
---

# T2167: Secure file storage

**Category:** CODE_FIX
**SD Elements:** [T2167](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T2167/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current, stable technology versions and Supabase for PostgreSQL, email and password login)
> Source: specs/PRD.md, line 5

> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
A public bucket (`getPublicUrl`) holding files named as uploaded (`John Doe ECG.pdf`), or files committed into `frontend/public/`. Anyone with the URL could read clinical files, and user-controlled names enable overwrites and path tricks.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('patient-files', 'patient-files', false, 10485760,
        array['image/png','image/jpeg','application/pdf']);

create table public.files (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references public.patients(id),
  object_key text not null unique,                 -- '<patient_id>/<uuid>' generated server-side
  display_name text not null check (display_name ~ '^[A-Za-z0-9 ._-]{1,100}$'),
  content_type text not null, size_bytes int not null, sha256 text not null,
  uploaded_by uuid not null references auth.users(id), created_at timestamptz default now()
);

-- Only the backend (service role) writes objects; clinicians read via signed URLs.
create policy "no direct client writes" on storage.objects for insert to authenticated
  with check (false);
create policy "read own-ward patient files" on storage.objects for select to authenticated
  using (bucket_id = 'patient-files'
         and public.can_access_patient(auth.uid(), (storage.foldername(name))[1]::uuid));
```
```python
# backend/app/services/files.py
import re, uuid
SAFE_NAME = re.compile(r"[^A-Za-z0-9 ._-]")
def object_key(patient_id: uuid.UUID) -> str:
    return f"{patient_id}/{uuid.uuid4().hex}"          # no user input in the key
def display_name(raw: str) -> str:
    name = SAFE_NAME.sub("_", raw.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])[:100].strip(". ")
    return name or "file"
```

**Implementation Guidance:**
- Buckets are private (`public = false`) with `file_size_limit` and `allowed_mime_types`; serve via `create_signed_url` with short expiry (≤ 5 min) after an authorization check (T162).
- Object keys are generated server-side (`<patient_id>/<uuid>`), never derived from the uploaded filename; keep the sanitized original name only as metadata (`display_name`), validated against an accepted-character allow-list.
- "DocumentRoot" equivalent: never place uploads in `frontend/public` or the Vite `dist/`, nor in the backend package; the Vercel filesystem is ephemeral anyway.
- Upload flow goes through the FastAPI backend (validation T54/T53) using the service role key kept only in backend env; storage RLS denies direct client writes.
- Record `sha256`, size and uploader in `public.files` and audit the upload (T45/T71).
- Reference: SD Elements guidance for T2167.

**Success Criteria:**
- [ ] Migration creates a private bucket with size/MIME limits and storage RLS policies.
- [ ] Integration test: anonymous/public URL fetch fails; signed URL works then expires.
- [ ] Test: an uploaded name like `../../evil.html` is stored with a random key and sanitized display name.

**Status:** Pending
