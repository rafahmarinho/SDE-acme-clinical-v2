"""API router: patient file attachments stored in the private Supabase Storage bucket.

* Type is decided from the file's magic bytes (never the client filename/extension or header).
* Size limited (5 MiB) by middleware and here; object names are server-generated UUIDs.
* Files are never served from the API origin; downloads use 60-second signed URLs.
"""

import hashlib
import uuid
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.core.audit import record_event
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.security import Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import AttachmentOut, SignedUrlOut

router = APIRouter(prefix="/v1/files", tags=["files"])
BUCKET = "clinical-files"
SIGNED_URL_SECONDS = 60
_SIGNATURES = ((b"%PDF-", "application/pdf", "pdf"), (b"\x89PNG\r\n\x1a\n", "image/png", "png"), (b"\xff\xd8\xff", "image/jpeg", "jpg"))


def sniff(head: bytes) -> tuple[str, str]:
    for magic, mime, ext in _SIGNATURES:
        if head.startswith(magic):
            return mime, ext
    raise DomainError("Only PDF, PNG and JPEG files are accepted.", 415)


def _storage_headers() -> dict[str, str]:
    key = get_settings().supabase_service_role_key.get_secret_value()
    return {"apikey": key, "Authorization": f"Bearer {key}"}


@router.get("/patients/{patient_id}", response_model=list[AttachmentOut])
async def list_files(patient_id: UUID, principal: Annotated[Principal, Depends(require(Perm.PATIENT_READ))]) -> list[AttachmentOut]:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """select id, original_name, content_type, size_bytes, created_at from public.attachments
               where patient_id = %s order by created_at desc limit 100""", (str(patient_id),))
    return [AttachmentOut(**r) for r in rows]


@router.post("/patients/{patient_id}", response_model=AttachmentOut, status_code=201)
async def upload_file(patient_id: UUID, request: Request, principal: Annotated[Principal, Depends(require(Perm.FILE_WRITE))],
                      file: Annotated[UploadFile, File()]) -> AttachmentOut:
    settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if not data or len(data) > settings.max_upload_bytes:
        raise DomainError("Files must be between 1 byte and 5 MB.", 413)
    mime, ext = sniff(data[:16])
    original = (file.filename or "upload").replace("\\", "/").split("/")[-1][:120] or "upload"
    async with transaction(principal) as conn:
        if await fetch_one(conn, "select 1 from public.patients where id = %s", (str(patient_id),)) is None:
            raise HTTPException(404, "Patient not found.")
        object_path = f"patients/{patient_id}/{uuid.uuid4()}.{ext}"
        async with httpx.AsyncClient(base_url=str(settings.supabase_url).rstrip("/"), timeout=20, verify=True) as client:
            resp = await client.post(f"/storage/v1/object/{BUCKET}/{object_path}", content=data,
                                     headers={**_storage_headers(), "Content-Type": mime, "x-upsert": "false"})
        if resp.status_code >= 400:
            raise DomainError("The file could not be stored. Please try again.", 502)
        row = await fetch_one(conn, """insert into public.attachments (patient_id, object_path, original_name, content_type,
               size_bytes, sha256, uploaded_by) values (%s, %s, %s, %s, %s, %s, %s)
               returning id, original_name, content_type, size_bytes, created_at""",
                              (str(patient_id), object_path, original, mime, len(data), hashlib.sha256(data).hexdigest(),
                               str(principal.user_id)))
        await record_event(principal, "file.uploaded", "patient", str(patient_id),
                           details={"attachment_id": str(row["id"]), "content_type": mime, "size": len(data)}, conn=conn,
                           request_id=request.state.request_id)
    return AttachmentOut(**row)


@router.get("/{attachment_id}/url", response_model=SignedUrlOut)
async def signed_url(attachment_id: UUID, request: Request,
                     principal: Annotated[Principal, Depends(require(Perm.PATIENT_READ))]) -> SignedUrlOut:
    settings = get_settings()
    async with transaction(principal) as conn:
        row = await fetch_one(conn, "select object_path, patient_id from public.attachments where id = %s", (str(attachment_id),))
        if row is None:
            raise HTTPException(404, "File not found.")
        async with httpx.AsyncClient(base_url=str(settings.supabase_url).rstrip("/"), timeout=10, verify=True) as client:
            resp = await client.post(f"/storage/v1/object/sign/{BUCKET}/{row['object_path']}",
                                     json={"expiresIn": SIGNED_URL_SECONDS}, headers=_storage_headers())
        if resp.status_code >= 400:
            raise DomainError("The file is temporarily unavailable.", 502)
        await record_event(principal, "file.accessed", "patient", str(row["patient_id"]),
                           details={"attachment_id": str(attachment_id)}, conn=conn, request_id=request.state.request_id)
    return SignedUrlOut(url=f"{str(settings.supabase_url).rstrip('/')}/storage/v1{resp.json()['signedURL']}",
                        expires_in=SIGNED_URL_SECONDS)
