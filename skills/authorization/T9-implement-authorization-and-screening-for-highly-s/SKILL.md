---
name: t9-implement-authorization-and-screening-for-highly-s
description: Require step-up re-authentication and anomaly screening for ACME Clinical high-sensitivity actions (changing alarm limits, resetting simulation data, staff role changes, break-glass), with a revocation list for compromised accounts.
---

# T9: Implement authorization and screening for highly sensitive transactions

**Category:** CODE_FIX
**SD Elements:** [T9](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T9/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you can create something very visual in 3D if")
> Source: specs/PRD.md, line 27

> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: "choose scenarios, advance the simulation, view events and reset the data. The results")
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
Changing alarm limits, resetting all data and changing staff roles would be one-click actions authorized only by the session. A hijacked or unattended session could widen SpO2 limits so real desaturations never alarm, or wipe the data. ACME Clinical has no monetary transactions; "high value" here means patient safety and data integrity.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
STEP_UP_MAX_AGE = timedelta(minutes=5)

def require_recent_auth(perm: Perm):
    async def checker(user=Depends(require(perm)), claims=Depends(jwt_claims)):
        # Supabase JWT "amr": [{"method": "password", "timestamp": 1731400000}]
        latest = max((a["timestamp"] for a in claims.get("amr", [])), default=0)
        if datetime.now(timezone.utc) - datetime.fromtimestamp(latest, timezone.utc) > STEP_UP_MAX_AGE:
            raise HTTPException(401, "Re-enter your password to continue",
                                headers={"WWW-Authenticate": 'Bearer error="step_up_required"'})
        if await is_revoked(user.id):          # revocation list for compromised accounts
            raise HTTPException(403, "Account suspended")
        return user
    return checker

# backend/app/routers/thresholds.py
@router.put("/thresholds/{tid}")
async def update(tid: UUID, body: ThresholdUpdate, request: Request,
                 user=Depends(require_recent_auth(Perm.THRESHOLD_WRITE))):
    risk = await screen_transaction(user, "threshold.update", body, request)  # anomaly rules
    if risk.block:
        raise HTTPException(409, "Change held for review by a second physician")
    ...
```

**Implementation Guidance:**
- Classify high-sensitivity actions: alarm threshold changes, simulation reset, staff role/activation changes, break-glass activation, device decommissioning.
- Step-up: frontend asks for the password again (`supabase.auth.signInWithPassword`) to refresh `amr`, or uses `supabase.auth.reauthenticate()` OTP; backend enforces recency as above.
- Revocation list: `security.revoked_accounts` table checked on every sensitive call (and in `get_current_user`).
- Screening in `backend/app/services/screening.py`: flag thresholds outside clinically plausible ranges (e.g. SpO2 low < 85 %), many changes in a short time, unusual hours, or source-country change using Vercel's `x-vercel-ip-country` header; hold or require second approval.
- Client malware detection is not applicable to this web stack; mitigate script injection with a strict CSP in `frontend/vercel.json`.
- Audit every sensitive action with before/after values.
- Reference: SD Elements guidance for T9.

**Success Criteria:**
- [ ] Sensitive endpoints return 401 `step_up_required` when the last password auth is older than 5 minutes.
- [ ] Suspended accounts cannot perform sensitive actions even with a valid JWT.
- [ ] Out-of-range threshold changes are held, logged and require a second physician.

**Status:** Applied
