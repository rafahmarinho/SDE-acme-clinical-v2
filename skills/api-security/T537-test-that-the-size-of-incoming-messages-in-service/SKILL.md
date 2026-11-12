---
name: t537-test-that-the-size-of-incoming-messages-in-service
description: Enforce and load-test maximum incoming message sizes for the ACME Clinical FastAPI API (body size middleware, Pydantic field and list limits, direct-to-Storage uploads) and bound responses from simulated external integrations.
---

# T537: Test that the size of incoming messages in services is restricted

**Category:** CODE_FIX
**SD Elements:** [T537](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T537/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: Allow binding a monitor to a bed, recording observations, acknowledging alarms and)
> Source: specs/PRD.md, line 33

> "persistidos, com integrações externas simuladas."
> (EN: persisted, with simulated external integrations.)
> Source: specs/PRD.md, line 9

**What the spec implies (naive approach):**
An observation endpoint with `text: str` and a simulation endpoint accepting `events: list[Event]` have no size bounds, so one request can carry megabytes of text or hundreds of thousands of items, which Pydantic parses fully in memory inside a short-lived Vercel function. Vercel caps function request bodies (4.5 MB), but that is far above what any ACME request needs and still allows expensive payloads. Simulated external integrations (device feeds) returning oversized data could have the same effect.

**Secure Implementation Pattern:**
```python
# backend/app/main.py
MAX_BODY = 64 * 1024        # 64 KB is ample for JSON commands; files go to Supabase Storage

class BodySizeLimit:
    def __init__(self, app): self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cl = dict(scope["headers"]).get(b"content-length")
        if cl and int(cl) > MAX_BODY:
            return await JSONResponse({"error": "payload_too_large"}, 413)(scope, receive, send)
        seen = 0
        async def limited():
            nonlocal seen
            msg = await receive(); seen += len(msg.get("body", b""))
            if seen > MAX_BODY: raise PayloadTooLarge()     # handled -> 413 (covers chunked bodies)
            return msg
        await self.app(scope, limited, send)

app.add_middleware(BodySizeLimit)

# backend/app/routers/observations.py
class ObservationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: int
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000, strip_whitespace=True)]
    tags: Annotated[list[Annotated[str, StringConstraints(max_length=32)]], Field(max_length=10)] = []
```

**Implementation Guidance:**
- Add the body-size middleware in `backend/app/main.py`; set per-route larger limits only where justified (none expected).
- Bound every Pydantic input model in `backend/app/routers/*`: `max_length` for strings, `Field(max_length=...)` for lists, `extra="forbid"`, numeric ranges for thresholds and simulation steps (e.g. `advance` steps 1-60).
- Files (PRD line 7 "arquivos"): upload directly from the SPA to Supabase Storage with a bucket `file_size_limit` and `allowed_mime_types`; the API only receives metadata.
- In `backend/app/services/simulation.py`, cap the size of data produced or consumed from simulated integrations (max events per tick, max response bytes with `httpx` streaming) so a malfunctioning "external" feed cannot exhaust memory.
- Tests: `backend/tests/test_message_size.py` sends bodies just under and over 64 KB (with and without `Content-Length`, chunked), strings over `max_length`, and oversized lists; expect `413`/`422` and no 500. Load test with k6 or JMeter against staging: ramp payload size and concurrency and confirm latency/error rate of normal requests stays stable.
- Reference: SD Elements guidance for T537.

**Success Criteria:**
- [ ] Requests over the limit get `413` before parsing; over-long fields get `422`.
- [ ] Chunked bodies without `Content-Length` are also limited.
- [ ] Load test report shows large payloads do not break or slow the service.
- [ ] Simulated integration responses are size-capped.

**Status:** Applied
