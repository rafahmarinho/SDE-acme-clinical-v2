---
name: t151-use-cryptographically-secure-random-numbers
description: Use only CSPRNGs (Python secrets/os.urandom, PostgreSQL gen_random_uuid, Web Crypto) for every ACME Clinical security value - request IDs, device secrets, one-time passwords, signed-URL paths, keys - and keep the random module confined to synthetic vital-sign simulation.
---

# T151: Use cryptographically secure random numbers

**Category:** CODE_FIX
**SD Elements:** [T151](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T151/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "frontend. A geração das leituras, os alarmes e os relatórios devem ser feitos em Python. A"
> (EN: frontend. The generation of readings, the alarms and the reports must be done in Python. The)
> Source: specs/PRD.md, line 21

**What the spec implies (naive approach):**
The simulation needs lots of randomness for readings, so a developer reaches for `random` everywhere and reuses it for monitor secrets, temporary passwords, file object names or request IDs. `random` is a seeded Mersenne Twister: its output can be predicted from observed values, making those identifiers guessable.

**Secure Implementation Pattern:**
```python
# Security values: secrets / os.urandom only
import secrets
request_id = secrets.token_hex(12)                       # backend/app/core/middleware.py
device_secret = secrets.token_urlsafe(32)                # backend/app/services/device_auth.py
object_path = f"patients/{patient_id}/{secrets.token_hex(16)}.{ext}"   # backend/app/services/files.py

# Synthetic vitals only: a dedicated, explicitly non-security PRNG
import random
_sim_rng = random.Random()                               # backend/app/services/simulation.py
heart_rate = round(_sim_rng.gauss(baseline_hr, 2.5))
```
```sql
-- Primary keys and tokens in PostgreSQL
id uuid primary key default gen_random_uuid()   -- pgcrypto CSPRNG, v4 UUID
```
```ts
// frontend: never Math.random() for anything security-relevant
const nonce = crypto.getRandomValues(new Uint8Array(16));
```

**Implementation Guidance:**
- Allow `import random` only in `backend/app/services/simulation.py` (synthetic readings, scenario jitter); everything else uses `secrets` (`backend/app/cli.py`, `backend/app/services/device_auth.py`, `backend/app/services/files.py`, `backend/app/core/middleware.py`, `backend/app/services/passwords.py::generate_password`).
- Generate keys with `cryptography`'s key generation (`backend/app/services/integrity.py`) or provision them from Vercel environment variables; derived keys use HKDF from a high-entropy secret, never from a user passphrase.
- All UUIDs in `supabase/migrations/*.sql` use `gen_random_uuid()`; never derive identifiers from time or sequence values exposed to users.
- Session IDs and refresh tokens are issued by Supabase Auth; do not mint session tokens in the app.
- In the frontend, ban `Math.random()` for IDs, nonces or tokens (ESLint `no-restricted-properties`), use `crypto.getRandomValues` / `crypto.randomUUID`.
- Reference: SD Elements guidance for T151.

**Success Criteria:**
- [ ] `backend/tests/test_secure_config.py::test_t587_random_module_only_for_synthetic_vitals` and `test_t587_security_values_use_csprng` pass.
- [ ] A static test greps `frontend/src` for `Math.random` and fails outside test files.
- [ ] Pytest: 1,000 generated device secrets / object paths are unique and have the expected length (>= 128 bits of entropy).

**Status:** Pending
