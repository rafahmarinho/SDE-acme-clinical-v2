"""API router: patient file attachments stored in the private Supabase Storage bucket.

* Every upload goes through `services.files.screen_upload`: size cap, malware scan, magic-byte
  type detection plus full structural validation, role-based type policy (T53/T54/T129).
  Rejections are security events, audited, and malware detections alert administrators.
* Object keys are server-generated UUID paths; clients only ever reference files by attachment
  UUID (no path parameters, T162). Stored keys are re-validated before use.
* Files are never served from the API origin; downloads use 60-second signed URLs that force
  `Content-Disposition: attachment` (T2167).
* Resources are released on every path: the upload stream is closed, HTTP clients are context
  managed, and an object stored before a failed DB insert is deleted again (T375).
"""

import hashlib
import logging
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from app.core.audit import notify_admins, record_event
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.logging import sec_event
from app.core.security import Perm, Principal, require
from app.core.validation import safe_filename
from app.db import fetch_all, fetch_one, transaction
from app.routers.break_glass import record_break_glass_use
from app.schemas import MAX_OFFSET, MAX_PAGE_SIZE, AttachmentOut, Page, SignedUrlOut
from app.services import files as file_service

router = APIRouter(prefix="/v1/files", tags=["files"])
log = logging.getLogger("acme.files")
BUCKET = "clinical-files"
SIGNED_URL_SECONDS = 60


def _storage_headers() -> dict[str, str]:
    key = get_settings().supabase_service_role_key.get_secret_value()
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _storage_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=str(get_settings().supabase_url).rstrip("/"), timeout=timeout, verify=True)


@router.get("/patients/{patient_id}", response_model=Page[AttachmentOut])
async def list_files(patient_id: UUID, request: Request,
                     principal: Annotated[Principal, Depends(require(Perm.PATIENT_READ))],
                     limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = MAX_PAGE_SIZE,
                     offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0) -> Page[AttachmentOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """select id, original_name, content_type, size_bytes, created_at from public.attachments
               where patient_id = %s order by created_at desc, id limit %s offset %s""", (str(patient_id), limit + 1, offset))
        if rows:
            await record_break_glass_use(conn, principal, patient_id, "files.listed", request.state.request_id)
    return Page[AttachmentOut](items=[AttachmentOut(**r) for r in rows[:limit]],
                               next_offset=offset + limit if len(rows) > limit else None)


async def _reject(principal: Principal, request: Request, patient_id: UUID, exc: file_service.FileRejected) -> None:
    level = logging.ERROR if exc.reason == "malware_detected" else logging.WARNING
    sec_event("upload_rejected" if exc.reason != "malware_detected" else "upload_malware_detected", outcome="failure",
              level=level, reason=exc.reason, scanner=file_service.get_scanner().name)
    await record_event(principal, "file.rejected", "patient", str(patient_id), outcome="failure", error_code=exc.reason,
                       request_id=request.state.request_id)
    if exc.reason == "malware_detected":
        await notify_admins("upload_malware_detected", {"patient_id": str(patient_id)})


@router.post("/patients/{patient_id}", response_model=AttachmentOut, status_code=201)
async def upload_file(patient_id: UUID, request: Request, principal: Annotated[Principal, Depends(require(Perm.FILE_WRITE))],
                      file: Annotated[UploadFile, File()]) -> AttachmentOut:
    try:
        data = await file.read(file_service.MAX_BYTES + 1)
        # Display-only name: basename, NFKC, conservative character set (never used as a storage key).
        original = safe_filename(file_service.display_name(file.filename), default="upload")
    finally:
        await file.close()
    try:
        mime, ext = await file_service.screen_upload(principal.role.value, data)
    except file_service.FileRejected as exc:
        await _reject(principal, request, patient_id, exc)
        raise
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.patients where id = %s", (str(patient_id),)) is None:
            raise HTTPException(404, "Patient not found.")
        object_path = file_service.new_object_path(patient_id, ext)
        async with _storage_client(20) as client:
            resp = await client.post(f"/storage/v1/object/{BUCKET}/{object_path}", content=data,
                                     headers={**_storage_headers(), "Content-Type": mime, "x-upsert": "false"})
            if resp.status_code >= 400:
                raise DomainError("The file could not be stored. Please try again.", 502)
            try:
                row = await fetch_one(conn, """insert into public.attachments (patient_id, object_path, original_name, content_type,
                       size_bytes, sha256, uploaded_by) values (%s, %s, %s, %s, %s, %s, %s)
                       returning id, original_name, content_type, size_bytes, created_at""",
                                      (str(patient_id), object_path, original, mime, len(data), hashlib.sha256(data).hexdigest(),
                                       str(principal.user_id)))
                await record_event(principal, "file.uploaded", "patient", str(patient_id),
                                   details={"attachment_id": str(row["id"]), "content_type": mime, "size": len(data)},
                                   conn=conn, request_id=request.state.request_id)
                await record_break_glass_use(conn, principal, patient_id, "file.uploaded", request.state.request_id)
            except BaseException:
                # Compensate: do not leave an orphaned object without metadata/audit.
                try:
                    await client.request("DELETE", f"/storage/v1/object/{BUCKET}", json={"prefixes": [object_path]},
                                         headers=_storage_headers())
                except httpx.HTTPError:
                    log.error("orphan_object_cleanup_failed", extra={"patient_id": str(patient_id)})
                raise
    return AttachmentOut(**row)


@router.get("/{attachment_id}/url", response_model=SignedUrlOut)
async def signed_url(attachment_id: UUID, request: Request,
                     principal: Annotated[Principal, Depends(require(Perm.PATIENT_READ))]) -> SignedUrlOut:
    settings = get_settings()
    async with transaction(principal) as conn:
        # RLS (can_access_patient) hides other wards' attachments: unknown and forbidden both return 404.
        row = await fetch_one(conn, "select object_path, patient_id from public.attachments where id = %s", (str(attachment_id),))
        if row is None:
            raise HTTPException(404, "File not found.")
        object_path = file_service.safe_object_path(row["object_path"])
        async with _storage_client(10) as client:
            resp = await client.post(f"/storage/v1/object/sign/{BUCKET}/{object_path}",
                                     json={"expiresIn": SIGNED_URL_SECONDS}, headers=_storage_headers())
        if resp.status_code >= 400:
            raise DomainError("The file is temporarily unavailable.", 502)
        await record_event(principal, "file.accessed", "patient", str(row["patient_id"]),
                           details={"attachment_id": str(attachment_id)}, conn=conn, request_id=request.state.request_id)
        await record_break_glass_use(conn, principal, row["patient_id"], "file.accessed", request.state.request_id)

    signed = resp.json().get("signedURL", "")
    if not isinstance(signed, str) or not signed.startswith(f"/object/sign/{BUCKET}/"):
        raise DomainError("The file is temporarily unavailable.", 502)
    download = quote(object_path.rsplit("/", 1)[-1])
    return SignedUrlOut(url=f"{str(settings.supabase_url).rstrip('/')}/storage/v1{signed}&download={download}",
                        expires_in=SIGNED_URL_SECONDS)
