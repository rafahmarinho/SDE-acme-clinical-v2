---
name: t34-refuse-overly-long-malformed-and-non-printable-cha
description: Refuses NUL, non-printable, malformed UTF-8 and overly long input in ACME Clinical text fields such as observations, search terms, names and notes, using shared Pydantic string types with max lengths.
---

# T34: Refuse overly-long, malformed, and non-printable characters unless required

**Category:** CODE_FIX
**SD Elements:** [T34](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T34/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "Permita vincular um monitor a um leito, registrar observações, reconhecer alarmes e"
> (EN: "Allow linking a monitor to a bed, recording observations, acknowledging alarms and")
> Source: specs/PRD.md, line 33

**What the spec implies (naive approach):**
Observations, alarm notes and maintenance notes are free text, so a developer would accept `text: str` of unlimited size. NUL bytes crash PostgreSQL inserts, bidi/zero-width characters can disguise content, and megabyte-sized notes inflate storage and Realtime broadcasts.

**Secure Implementation Pattern:**
```python
# backend/app/schemas/text.py
import re, unicodedata
from typing import Annotated
from pydantic import AfterValidator, StringConstraints

_FORBIDDEN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F​-‏‪-‮⁦-⁩﻿]")

def _clean(v: str) -> str:
    v = unicodedata.normalize("NFC", v)
    if _FORBIDDEN.search(v):
        raise ValueError("contains non-printable characters")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in v):
        raise ValueError("malformed unicode")
    return v

def _single_line(v: str) -> str:
    if any(c in v for c in "\r\n\t"):
        raise ValueError("line breaks not allowed")
    return _clean(v)

def Text(max_len: int, multiline: bool = False):
    s = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_len)]
    return Annotated[s, AfterValidator(_clean if multiline else _single_line)]

ObservationText = Text(2000, multiline=True)   # \t \n \r allowed
SearchTerm = Text(100)                          # single line
PersonName = Text(120)
```

**Implementation Guidance:**
- Define shared string types in `backend/app/schemas/` and use them everywhere instead of bare `str`; single-line fields reject newlines, multi-line fields allow only `\t\n\r`.
- Reject NUL (`%00`) and other C0/C1 controls, bidi overrides and zero-width characters unless a field genuinely needs them.
- Starlette decodes JSON as UTF-8 and fails on malformed bytes; keep that behavior and ensure the error handler returns 422, not 500.
- Enforce a global request body size limit (e.g. 1 MB, larger only for upload routes) in middleware in `backend/app/main.py`.
- Mirror max lengths in React inputs (`maxLength`) and as `char_length` CHECKs in `supabase/migrations/0001_schema.sql`.
- Reference: SD Elements guidance for T34.

**Success Criteria:**
- [ ] Tests: observation containing `\x00`, `‮` or 2001 characters returns 422; a multi-line valid note is accepted.
- [ ] Invalid UTF-8 request bodies return 4xx, never 500.
- [ ] Requests over the body size limit are rejected with 413.

**Status:** Applied
