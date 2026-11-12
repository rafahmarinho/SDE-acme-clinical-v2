---
name: t1038-make-homoglyphs-distinguishable-when-showing-them
description: Makes homoglyphs distinguishable in ACME Clinical when displaying staff names, emails, patient identifiers and bed/monitor codes, so look-alike Unicode characters cannot impersonate users or cause actions on the wrong patient.
---

# T1038: Make homoglyphs distinguishable when showing them to users

**Category:** CODE_FIX
**SD Elements:** [T1038](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T1038/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you may create something very visual in 3D if")
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
Staff management lets administrators create users and assign roles, and observations/acknowledgements show who acted. If a user can set a display name or email with Cyrillic "а" instead of Latin "a", they can impersonate a colleague in audit trails; look-alike patient MRNs or bed codes could cause a monitor to be linked to the wrong patient.

**Secure Implementation Pattern:**
```python
# backend/app/schemas/identifiers.py
import unicodedata
from pydantic import AfterValidator
from typing import Annotated

def _scripts(s: str) -> set[str]:
    out = set()
    for ch in s:
        if ch.isalpha():
            out.add(unicodedata.name(ch, "UNKNOWN").split(" ")[0])  # LATIN, CYRILLIC, GREEK...
    return out

def ascii_identifier(v: str) -> str:            # MRN, bed code, monitor serial
    if not v.isascii():
        raise ValueError("identifiers must be ASCII")
    return v

def single_script_name(v: str) -> str:          # staff / patient display names
    v = unicodedata.normalize("NFKC", v)
    if len(_scripts(v)) > 1:
        raise ValueError("mixed character sets are not allowed")
    return v

Identifier = Annotated[str, AfterValidator(ascii_identifier)]
DisplayName = Annotated[str, AfterValidator(single_script_name)]
```
```tsx
// frontend/src/components/UserBadge.tsx - flag non-ASCII and show punycode for email domains
import { toASCII } from "punycode/";
export const UserBadge = ({ name, email }: { name: string; email: string }) => {
  const [local, domain] = email.split("@");
  const nonAscii = /[^\x00-\x7F]/.test(name + email);
  return <span title={nonAscii ? "Contains non-Latin characters" : undefined}>
    {name} &lt;{local}@{toASCII(domain ?? "")}&gt;{nonAscii && " (non-Latin)"}</span>;
};
```

**Implementation Guidance:**
- Restrict security-relevant identifiers (patient MRN, bed/monitor codes, device serials) to ASCII allow-lists in Pydantic models and CHECK constraints.
- For names, apply NFKC normalization and reject mixed-script values; show a warning badge when non-Latin characters are present in staff or patient names.
- Display email domains in Punycode (RFC 3492) in staff management and audit views; enforce uniqueness on a normalized/skeleton form of emails and names to prevent look-alike duplicates.
- Use a font with clearly distinct glyphs (0/O, l/1/I) for identifiers on monitor and bed screens.
- Reference: SD Elements guidance for T1038.

**Success Criteria:**
- [ ] Creating staff named `Аdmin` (Cyrillic А) alongside `Admin` is rejected or visibly flagged.
- [ ] Non-ASCII MRN/bed codes return 422.
- [ ] Email domains with IDN characters render as `xn--` Punycode in staff screens.

**Status:** Applied
