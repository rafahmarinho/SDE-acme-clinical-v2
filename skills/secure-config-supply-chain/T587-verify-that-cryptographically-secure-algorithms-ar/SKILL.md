---
name: t587-verify-that-cryptographically-secure-algorithms-ar
description: Test recipe verifying ACME Clinical uses Python's secrets module (and Web Crypto in the frontend) for all security-relevant random values, while the random module is confined to synthetic vital-sign and ECG simulation.
---

# T587: Verify that cryptographically secure algorithms are used for random number generation

**Category:** CODE_FIX
**SD Elements:** [T587](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T587/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: frontend. Reading generation, alarms and reports must be done in Python. The)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
The simulator in Python will rely heavily on `random` to generate readings, and developers tend to reuse the same `random` calls for patient pseudonyms, invite tokens, cron secrets or report download IDs. `random` (Mersenne Twister) is predictable and must not be used for security values; `Math.random()` in the frontend has the same problem.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py  -- security-relevant randomness
import secrets

def new_patient_ref() -> str:
    return "PT-" + secrets.token_hex(8)

def new_invite_token() -> str:
    return secrets.token_urlsafe(32)

# backend/app/services/simulation.py  -- synthetic data only (not security)
import random
_rng = random.Random()  # noqa: S311  synthetic vitals/ECG, never for IDs or tokens

def next_heart_rate(base: int) -> int:
    return max(30, min(200, base + _rng.randint(-3, 3)))
```

```python
# backend/tests/test_secure_random.py
import pathlib, re

ALLOWED = {pathlib.Path("app/services/simulation.py")}

def test_random_module_only_in_simulation():
    for f in pathlib.Path("app").rglob("*.py"):
        src = f.read_text()
        if re.search(r"^\s*(import random|from random import)", src, re.M):
            assert f in ALLOWED, f"insecure random in {f}"
```

**Implementation Guidance:**
- Inventory all random generation: `rg "import random|random\.|uuid1|Math.random" backend frontend/src supabase`.
- Use `secrets` / `uuid.uuid4()` (backend) and `crypto.randomUUID()` / `crypto.getRandomValues()` (frontend) for IDs, tokens, nonces; `gen_random_uuid()` in PostgreSQL defaults.
- Allow `random` only in `backend/app/services/simulation.py` with an explicit `# noqa: S311` comment; run Bandit (`bandit -r backend/app`) or Ruff `S311` in CI.
- Add an ESLint `no-restricted-properties` rule banning `Math.random` outside simulation-display code in `frontend/`.
- Do not seed security RNGs manually.
- Reference: SD Elements guidance for T587.

**Success Criteria:**
- [ ] `backend/tests/test_secure_random.py` passes.
- [ ] Ruff/Bandit S311 reports no findings outside the simulation module.
- [ ] All IDs/tokens use `secrets`, `uuid4`, `gen_random_uuid` or Web Crypto.
- [ ] ESLint rule blocks `Math.random` in security-relevant frontend code.

**Status:** Applied
