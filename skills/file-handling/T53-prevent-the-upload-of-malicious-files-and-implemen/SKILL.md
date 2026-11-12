---
name: t53-prevent-the-upload-of-malicious-files-and-implemen
description: Restricts who can upload which file types in ACME Clinical by role and adds a malware scanning step (simulated scanner interface with EICAR detection in the demo, pluggable ClamAV/third-party API in production) before files are committed to Supabase Storage.
---

# T53: Prevent the upload of malicious files and implement anti-malware solutions

**Category:** CODE_FIX
**SD Elements:** [T53](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T53/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

> "persistidos, com integrações externas simuladas. Organize o projeto em telas, componentes,"
> (EN: persisted, with simulated external integrations. Organize the project into screens, components,)
> Source: specs/PRD.md, line 9

**What the spec implies (naive approach):**
Any authenticated user can upload any file which is then downloaded by other clinicians. With no scanning, the app becomes a malware distribution point inside a hospital network.

**Secure Implementation Pattern:**
```python
# backend/app/services/files.py
from typing import Protocol
from fastapi import HTTPException

UPLOAD_POLICY = {   # configurable: role -> allowed detected MIME types
    "nurse": {"image/png", "image/jpeg"},
    "physician": {"image/png", "image/jpeg", "application/pdf"},
    "biomed": {"application/pdf"},                 # maintenance documents
    "admin": {"image/png", "image/jpeg", "application/pdf"},
}

class Scanner(Protocol):
    async def scan(self, data: bytes) -> bool: ...   # True = clean

class SimulatedScanner:  # PRD: external integrations are simulated
    EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    async def scan(self, data: bytes) -> bool:
        return self.EICAR not in data

async def accept_upload(user, data: bytes, detected_mime: str, scanner: Scanner):
    if detected_mime not in UPLOAD_POLICY.get(user.role, set()):
        raise HTTPException(415, "File type not allowed.")
    if not await scanner.scan(data):
        sec_event("upload_malware_detected", outcome="fail", user_id=user.id, ip=None, mime=detected_mime)
        raise HTTPException(422, "File rejected by security scan.")
```

**Implementation Guidance:**
- Define a role-based upload policy (store in a `upload_policy` table editable by admins, audited) and enforce it in the backend upload route; frontend hides upload where not allowed but the backend is authoritative.
- Scan every upload before writing to Storage. Demo: `SimulatedScanner` (detects EICAR) consistent with "integrações externas simuladas". Production: ClamAV cannot run inside Vercel functions — use an external scanning service/API (or a Supabase Storage webhook to a scanner) behind the same `Scanner` interface; quarantine bucket until clean.
- Log detections as security events (T45) and alert administrators.
- Combine with content validation (T54), size limits and private storage (T2167).
- Network/host anti-malware and removable media controls are organizational/endpoint concerns outside this repo — document as not applicable to the codebase.
- Reference: SD Elements guidance for T53.

**Success Criteria:**
- [ ] Upload route enforces `UPLOAD_POLICY` by role (tests per role).
- [ ] EICAR upload rejected and logged (T107 test).
- [ ] Scanner is injectable; production scanner choice documented in README.

**Status:** Applied
