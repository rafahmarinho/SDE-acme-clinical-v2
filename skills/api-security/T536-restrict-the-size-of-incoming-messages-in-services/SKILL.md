---
name: t536-restrict-the-size-of-incoming-messages-in-services
description: Restrict the size of incoming messages to the ACME Clinical FastAPI service (JSON bodies, uploads, header and URL sizes, string/array lengths, JSON nesting) and of payloads it forwards to Supabase, rejecting oversize requests with 413/414/431/422 before parsing.
---

# T536: Restrict the size of incoming messages in services

**Category:** CODE_FIX
**SD Elements:** [T536](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T536/)
**Priority:** 8/10 · **Phase:** requirements

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: Use current, stable versions of the technologies and Supabase for PostgreSQL, email and password login, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
FastAPI reads the whole request body into memory before Pydantic validates it, and file uploads via `UploadFile` spool arbitrarily large content. Without explicit limits, a single request with a 100 MB JSON array of observations, deeply nested JSON or a giant attachment can exhaust the serverless function's memory and the Supabase Storage quota.

**Secure Implementation Pattern:**
```python
# backend/app/core/middleware.py - pure ASGI, counts bytes as they stream in
MAX_JSON_BODY_BYTES = 64 * 1024
MAX_UPLOAD_BYTES = 5 * 1024 * 1024 + 64 * 1024          # file limit + multipart overhead

class BodySizeLimitMiddleware:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = MAX_UPLOAD_BYTES if scope["path"].startswith("/files/") else MAX_JSON_BODY_BYTES
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and int(declared) > limit:
            return await _error("Request body too large", 413)(scope, receive, send)
        seen = 0
        async def limited_receive():
            nonlocal seen
            msg = await receive()
            seen += len(msg.get("body", b""))
            if seen > limit:
                raise _TooLarge()
            return msg
        try:
            await self.app(scope, limited_receive, send)
        except _TooLarge:
            await _error("Request body too large", 413)(scope, receive, send)

# backend/app/schemas/__init__.py - per-field limits
class ObservationIn(Strict):
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    tags: Annotated[list[ShortText], Field(max_length=10)] = []
```

**Implementation Guidance:**
- Keep `BodySizeLimitMiddleware` (streaming byte count + `Content-Length` precheck) outermost in `backend/app/main.py`; route-specific limits for `/files/...` uploads (`MAX_BYTES` in `backend/app/services/files.py`) versus JSON routes.
- Enforce `MAX_HEADER_COUNT`, `MAX_HEADER_BYTES`, `MAX_URL_BYTES` (`backend/app/core/middleware.py`) and JSON depth (`MAX_JSON_DEPTH`, `parse_json_object` in `backend/app/core/validation.py`).
- Give every string and list in request models a `max_length` (observations, ack notes, names, search terms, array of monitor IDs) in `backend/app/schemas/__init__.py`.
- Bound outbound payloads too: Storage upload size, rows per CSV export (`MAX_AUDIT_ROWS`), Realtime broadcast payload size.
- Vercel caps function request bodies (~4.5 MB) - keep the app limits below or consistent with it, and set Supabase Storage bucket `file_size_limit` in migrations/config.
- Reference: SD Elements guidance for T536.

**Success Criteria:**
- [ ] Pytest (`backend/tests/test_api_security.py`): 65 KB JSON -> 413; chunked body without `Content-Length` over the limit -> 413; 6 MB upload -> 413; 200-level nested JSON -> 400/422.
- [ ] Every `str`/`list` field in request models has a maximum length (introspection test).
- [ ] Storage bucket `file_size_limit` matches `MAX_BYTES`.

**Status:** Applied
