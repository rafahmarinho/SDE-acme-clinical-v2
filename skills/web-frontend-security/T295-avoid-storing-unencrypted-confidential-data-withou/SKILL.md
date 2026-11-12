---
name: t295-avoid-storing-unencrypted-confidential-data-withou
description: Avoid storing ACME Clinical confidential data (PHI attachments, generated reports, device secrets, signing keys, service-role key) unencrypted or in shared locations: private Supabase Storage buckets with RLS, hashed device secrets, secrets only in Vercel env, owner-only temp files, and nothing sensitive in the browser bundle.
---

# T295: Avoid storing unencrypted confidential data without access control mechanisms

**Category:** CODE_FIX
**SD Elements:** [T295](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T295/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: Use current, stable versions of the technologies and Supabase for PostgreSQL, email and password login, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
Files are stored in a public Supabase bucket for easy `<img src>` display, reports are written to `/tmp/report.csv` (shared across invocations on the same instance), monitor API keys are stored in plain text, and app secrets end up in `VITE_*` variables or committed `.env` files. Any of these exposes PHI or keys without access control.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0007_privacy.sql (pattern) - private bucket + RLS on storage.objects
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('clinical-files', 'clinical-files', false, 5242880, array['application/pdf','image/png','image/jpeg'])
on conflict (id) do update set public = false;
-- no policies for anon/authenticated on storage.objects for this bucket: only signed URLs issued by the API
```
```python
# backend/app/services/device_auth.py - store only a hash of device secrets
def new_device_secret() -> tuple[str, bytes]:
    secret = secrets.token_urlsafe(24)
    return secret, hash_device_secret(secret)      # show once, persist only the hash

# backend/app/services/reports.py - private, owner-only temp files, deleted after use
@contextmanager
def private_workdir():
    with tempfile.TemporaryDirectory(prefix="acme-", dir=_ensure_root()) as d:
        os.chmod(d, 0o700)
        yield d
```

**Implementation Guidance:**
- Two classes of confidential data: application secrets (`SUPABASE_SERVICE_ROLE_KEY`, JWT secret, `AUDIT_SIGNING_KEY`, DB password) and user/patient data (attachments, reports, observations). Classify in `docs/security/data-classification.md`.
- Secrets live only in Vercel encrypted env vars / local `.env` (git-ignored), loaded as `SecretStr` in `backend/app/core/config.py`; frontend gets only the Supabase URL and anon key (`frontend/src/lib/supabase.ts`).
- Attachments: private bucket, server-generated paths, signed URLs (T50); Supabase encrypts storage and DB at rest at the platform level.
- Device secrets and any API tokens are stored hashed (`backend/app/services/device_auth.py`); highly sensitive fields that must be reversible use `pgcrypto`/Supabase Vault rather than plain columns.
- Temporary report files use `private_workdir`, `create_exclusive` (`O_EXCL`, mode `0600`) and are deleted after streaming (`sweep_expired`).
- Do not persist serialized objects with confidential fields (pickles, JSON dumps) to disk or browser storage (T1468).
- Reference: SD Elements guidance for T295.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_files.py`): report temp files are created with mode `0600` in a `0700` dir and removed after download.
- [ ] SQL check: `select public from storage.buckets where id = 'clinical-files'` is false; `monitors` has no plaintext secret column.
- [ ] `pnpm build` output contains no service-role key or `AUDIT_SIGNING_KEY` (grep on `frontend/dist`).

**Status:** Pending
