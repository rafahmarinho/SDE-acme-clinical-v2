# File handling

Covers T53, T54, T107, T129, T157, T162, T297, T300, T345, T346, T375, T572, T595, T2167.
Code: `backend/app/services/files.py`, `backend/app/routers/files.py`,
`backend/app/services/reports.py` (temp files), `backend/app/services/{alarms,simulation,integrity}.py`
(configuration integrity). Tests: `backend/tests/test_files.py`.

## Upload pipeline (T53, T54, T107, T129)

Single upload point: `POST /v1/files/patients/{patient_id}` (nurse/physician). The browser has no
Storage write path: the `clinical-files` bucket is private with a 5 MB limit and a MIME allow-list,
and no `storage.objects` policy exists for anon/authenticated (direct uploads are denied).

1. Read at most 5 MiB + 1 byte (the middleware also caps the body).
2. Malware scan on the raw bytes via the `Scanner` protocol. The default `SignatureScanner`
   (simulated AV, consistent with the PRD's simulated integrations) rejects EICAR, PE/ELF
   executables and script markers. **Production:** ClamAV cannot run inside Vercel functions —
   register an external scanning API client with `services.files.set_scanner(...)` (same
   interface). Scanner errors fail closed (503).
3. Type from magic bytes only (filename/extension/Content-Type ignored), then a full structural
   parse: PNG chunk walk with CRC and IHDR/IEND, JPEG marker walk to EOI, PDF header/`%%EOF`;
   rejects truncated files, trailing data (polyglots), decompression-bomb dimensions (> 40 MP),
   PDFs with JavaScript/launch/embedded files/forms and encrypted PDFs.
4. Role policy (`UPLOAD_POLICY`) on the detected type.
5. Rejections are security events + audited `file.rejected` with the reason; malware also raises
   an admin alert.

Network/host anti-malware and removable media controls are endpoint/IT concerns outside this repo.

## Storage (T2167, T162, T297)

Object keys are generated server-side: `patients/<patient uuid>/<uuid>.<ext>` (DB check constraint
enforces the pattern). The original name is kept only as sanitized display metadata. Clients refer
to files by attachment UUID only; no route accepts a path, key or template name (tested). Stored
keys are re-validated before use. Downloads use 60 s signed URLs with `download=` (attachment
disposition) after an RLS-scoped lookup (other wards' files → 404). SHA-256, size, uploader are
recorded and the upload is audited. Uploads never live in `frontend/public`, `dist/` or the
backend package.

Bucket privacy is verified before it is relied on (T214): before any upload or signed URL the API reads
`GET /storage/v1/bucket/clinical-files` and requires `public == false` (cached 5 minutes per instance). A public or
unverifiable bucket is a `storage_bucket_not_private` security event, raises an admin alert and the request fails
closed with 503 `storage_unavailable`. Signed URLs and file contents are never logged.

## Temporary files (T157, T300, T572, T595)

Only CSV exports (`GET /v1/reports/export.csv?kind=ward_activity|audit_events`) touch the
filesystem. Each export: `sweep_expired()` (dirs older than 10 min removed, planted symlinks
unlinked without following), `tempfile.mkdtemp` (random name, 0700) under
`<tmp>/acme-reports`, the file created with `O_CREAT|O_EXCL|O_NOFOLLOW` (0600), sent with
`FileResponse`, and the directory removed by a `BackgroundTask` after sending (or immediately on
render/audit failure). `open_no_follow` rejects symlinks, non-regular files and hard links. The
workspace root itself must be a real directory owned by the API process with mode 0700
(`check_private_dir`): a pre-created, world-writable or foreign-owned root is refused.
Symlink tests run on Linux CI (skipped on Windows dev machines). Report kinds come from an enum.

## Configuration integrity (T345, T346)

* Alarm thresholds carry `integrity_mac` = HMAC-SHA256 (key `CONFIG_INTEGRITY_KEY`, or HKDF-derived
  from the JWT secret) over id/scope/parameter/limits/updated_at, written by the backend
  (`alarms.seal_threshold`). On every evaluation, rows with a bad MAC — or unsigned rows that differ
  from the seeded safe defaults — are ignored (ward value or `SAFE_DEFAULT_LIMITS` stays in
  force), a `config_integrity_violation` security event is logged and admins are alerted.
* The simulation state row carries a MAC re-sealed on every scenario change/tick/reset; a
  tampered state refuses to run (503 `integrity_violation`) until an admin resets it.
* Uploaded files: SHA-256 stored at upload; files are not re-used server-side (reports never
  embed attachments), so verification on use is not applicable today.
* Bundled config (`vercel.json`, Python settings) is immutable in the Vercel deployment; there are
  no runtime-writable config files.

## Releasing resources (T375)

DB connections come from a bounded pool and are always used via `async with transaction(...)`;
HTTP clients are context managed; the upload stream is closed in `finally`; an object stored
before a failed metadata insert is deleted again; temp dirs are removed as above.
Frontend Realtime channels/intervals/3D scenes must be disposed in effect cleanups (frontend owner).
