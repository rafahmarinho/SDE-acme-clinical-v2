"""Upload validation, malware scanning and storage naming for clinical attachments.

Pipeline (T53/T54/T129/T2167), all server-side; the client filename, extension and
Content-Type header are never trusted:

1. read with a hard size cap (5 MiB, also enforced by middleware);
2. malware scan on the raw bytes through the pluggable `Scanner` interface (default:
   `SignatureScanner`, EICAR + known-dangerous signatures; production: plug an external AV API
   via `set_scanner`, see docs/security/file-handling.md). A scanner failure rejects the upload;
3. type detection from magic bytes, then a structural parse of the whole file (PNG chunk/CRC
   walk, JPEG marker walk, PDF header/trailer) that rejects truncated files, trailing data
   (polyglots), active PDF content (JavaScript, launch actions, embedded files) and encryption;
4. role-based upload policy on the *detected* type;
5. storage under a server-generated object key `patients/<patient uuid>/<uuid>.<ext>`; the
   sanitized original name is kept only as display metadata.
"""

from __future__ import annotations

import re
import struct
import zlib
from typing import Protocol
from uuid import UUID, uuid4

from app.core.errors import DomainError

MAX_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
SIGNATURES = ((b"%PDF-", "application/pdf", "pdf"), (PNG_MAGIC, "image/png", "png"), (b"\xff\xd8\xff", "image/jpeg", "jpg"))

# Role -> detected MIME types that role may upload (backend is authoritative; UI only hides).
UPLOAD_POLICY: dict[str, frozenset[str]] = {
    "nurse": frozenset({"image/png", "image/jpeg", "application/pdf"}),
    "physician": frozenset({"image/png", "image/jpeg", "application/pdf"}),
    "biomed_tech": frozenset(),
    "admin": frozenset(),
}

OBJECT_PATH = re.compile(r"^patients/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
                         r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|png|jpg)$")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9 ._()-]")
_PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia|XFA|SubmitForm|ImportData)\b")


class FileRejected(DomainError):
    def __init__(self, message: str, status_code: int = 422, reason: str = "invalid_content"):
        super().__init__(message, status_code, code=reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Malware scanning (T53)
# ---------------------------------------------------------------------------
class Scanner(Protocol):
    name: str

    async def scan(self, data: bytes) -> bool:  # True = clean
        ...


class SignatureScanner:
    """Simulated AV (PRD: external integrations are simulated). Detects the EICAR test file and a
    few executable/script signatures anywhere in the content."""

    name = "signature"
    EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    PATTERNS = (EICAR, b"TVqQAAMAAAAEAAAA", b"<script", b"<?php", b"#!/bin/")

    async def scan(self, data: bytes) -> bool:
        lowered = data.lower()
        return not any((p.lower() in lowered) for p in self.PATTERNS) and not data.startswith((b"MZ", b"\x7fELF"))


_scanner: Scanner = SignatureScanner()


def set_scanner(scanner: Scanner) -> None:
    """Plug in a production scanner (e.g. an external AV API client) behind the same interface."""
    global _scanner
    _scanner = scanner


def get_scanner() -> Scanner:
    return _scanner


# ---------------------------------------------------------------------------
# Content validation (T54)
# ---------------------------------------------------------------------------
def sniff(head: bytes) -> tuple[str, str]:
    for magic, mime, ext in SIGNATURES:
        if head.startswith(magic):
            return mime, ext
    raise FileRejected("Only PDF, PNG and JPEG files are accepted.", 415, "unsupported_type")


def _validate_png(data: bytes) -> None:
    pos, first, seen_end = len(PNG_MAGIC), True, False
    while pos + 12 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + length
        if end > len(data):
            raise ValueError("truncated chunk")
        chunk = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:end])
        if zlib.crc32(ctype + chunk) & 0xFFFFFFFF != crc:
            raise ValueError("bad crc")
        if first:
            if ctype != b"IHDR" or length != 13:
                raise ValueError("IHDR must be first")
            width, height = struct.unpack(">II", chunk[:8])
            if not (0 < width and 0 < height and width * height <= MAX_IMAGE_PIXELS):
                raise ValueError("bad dimensions")
            first = False
        pos = end
        if ctype == b"IEND":
            seen_end = True
            break
    if not seen_end or pos != len(data):
        raise ValueError("missing IEND or trailing data")


def _validate_jpeg(data: bytes) -> None:
    if not data.endswith(b"\xff\xd9"):
        raise ValueError("missing EOI or trailing data")
    pos, saw_frame = 2, False
    while pos < len(data):
        if data[pos] != 0xFF:
            raise ValueError("bad marker")
        marker = data[pos + 1] if pos + 1 < len(data) else 0
        if marker == 0xD9:
            break
        if marker in (0x01, *range(0xD0, 0xD8)):
            pos += 2
            continue
        if pos + 4 > len(data):
            raise ValueError("truncated")
        (seg_len,) = struct.unpack(">H", data[pos + 2:pos + 4])
        if seg_len < 2 or pos + 2 + seg_len > len(data):
            raise ValueError("bad segment")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
            if not (0 < width and 0 < height and width * height <= MAX_IMAGE_PIXELS):
                raise ValueError("bad dimensions")
            saw_frame = True
        if marker == 0xDA:  # start of scan: entropy-coded data until EOI
            if not saw_frame:
                raise ValueError("scan before frame")
            return
        pos += 2 + seg_len
    raise ValueError("no image data")


def _validate_pdf(data: bytes) -> None:
    if not re.match(rb"%PDF-[12]\.\d", data[:8]):
        raise ValueError("bad header")
    tail = data[-1024:].rstrip(b"\r\n\x00 \t")
    if not tail.endswith(b"%%EOF"):
        raise ValueError("missing EOF or trailing data")
    if _PDF_ACTIVE.search(data):
        raise ValueError("active content")
    if b"/Encrypt" in data:
        raise ValueError("encrypted")
    if b"/Type" not in data or b"/Page" not in data:
        raise ValueError("no pages")


_VALIDATORS = {"image/png": _validate_png, "image/jpeg": _validate_jpeg, "application/pdf": _validate_pdf}


def validate_content(data: bytes) -> tuple[str, str]:
    """Return (detected mime, extension) or raise FileRejected. Never trusts name or header."""
    if not data or len(data) > MAX_BYTES:
        raise FileRejected("Files must be between 1 byte and 5 MB.", 413, "too_large")
    mime, ext = sniff(data[:16])
    try:
        _VALIDATORS[mime](data)
    except (ValueError, struct.error, IndexError) as exc:
        raise FileRejected("The file content is invalid or not allowed.", 422, "invalid_content") from exc
    return mime, ext


async def screen_upload(role: str, data: bytes) -> tuple[str, str]:
    """Full pipeline: size, malware scan (on raw bytes, first), structure, role policy."""
    if not data or len(data) > MAX_BYTES:
        raise FileRejected("Files must be between 1 byte and 5 MB.", 413, "too_large")
    try:
        clean = await get_scanner().scan(data)
    except Exception as exc:  # fail closed: an unavailable scanner never lets a file through
        raise FileRejected("Files cannot be scanned right now. Please try again later.", 503, "scanner_unavailable") from exc
    if not clean:
        raise FileRejected("The file was rejected by the security scan.", 422, "malware_detected")
    mime, ext = validate_content(data)
    if mime not in UPLOAD_POLICY.get(role, frozenset()):
        raise FileRejected("You are not allowed to upload this type of file.", 415, "type_not_allowed")
    return mime, ext


# ---------------------------------------------------------------------------
# Naming / paths (T2167, T162)
# ---------------------------------------------------------------------------
def display_name(raw: str | None) -> str:
    base = (raw or "").replace("\\", "/").split("/")[-1]
    name = _UNSAFE_NAME.sub("_", base)[:120].strip(". ")
    return name or "upload"


def new_object_path(patient_id: UUID, ext: str) -> str:
    path = f"patients/{patient_id}/{uuid4()}.{ext}"
    if not OBJECT_PATH.match(path):
        raise ValueError("unexpected object path")
    return path


def safe_object_path(path: str) -> str:
    """Re-validate a stored object key before using it with Storage (defence against tampered rows)."""
    if not isinstance(path, str) or not OBJECT_PATH.match(path) or ".." in path:
        raise FileRejected("The file is unavailable.", 404, "not_found")
    return path
