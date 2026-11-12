---
name: t85-test-server-side-enforcement-of-authorization
description: Test that ACME Clinical enforces role permissions on the FastAPI server and in Supabase RLS, so forged or replayed requests from a lower-privileged role (e.g. a nurse changing alarm limits) are rejected even when the UI hides the action.
---

# T85: Test server-side enforcement of authorization

**Category:** CODE_FIX
**SD Elements:** [T85](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T85/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "filtros, estados de carregamento e mensagens de erro. Adapte a navegação aos perfis de"
> (EN: "...filters, loading states and error messages. Adapt the navigation to the user profiles")
> Source: specs/PRD.md, line 13

**What the spec implies (naive approach):**
Adapting navigation per profile is easy to mistake for access control. If the "Thresholds" or "Staff" screens are just hidden, a nurse replaying the physician's request through a proxy (or calling Supabase directly with the anon key and their JWT) would succeed.

**Secure Implementation Pattern:**
```python
# backend/tests/test_server_side_authz.py
async def test_nurse_cannot_replay_physician_threshold_change(client_as, physician, nurse, threshold):
    body = {"spo2_low": 80, "hr_high": 180}
    ok = await client_as(physician).put(f"/api/thresholds/{threshold.id}", json=body)
    assert ok.status_code == 200
    # Same request, lower-privileged token (what a proxy tamper would produce)
    r = await client_as(nurse).put(f"/api/thresholds/{threshold.id}", json=body)
    assert r.status_code == 403

async def test_direct_supabase_bypass_blocked(supabase_as):
    sb = supabase_as("nurse")                     # anon key + nurse JWT, no backend
    res = sb.table("alarm_thresholds").update({"spo2_low": 50}).eq("id", THRESHOLD_ID).execute()
    assert res.data == []                         # RLS: zero rows affected

async def test_header_tampering_ignored(client_as, nurse):
    r = await client_as(nurse).post("/api/simulation/reset",
                                    headers={"X-Role": "administrator", "X-User-Id": ADMIN_ID})
    assert r.status_code == 403
```

**Implementation Guidance:**
- For every privileged action (threshold change, staff role change, simulation reset/advance, device deletion, monitor binding) record the legitimate request and replay it with each lower role's token.
- Test the Supabase path directly (anon key + user JWT) for tables and Realtime channels, because the frontend may use Supabase Realtime; RLS must block what the API blocks.
- Manually confirm with an HTTP proxy (Burp/ZAP) against a Vercel preview deployment; document results in `backend/tests/README` or the security test log.
- Ensure identity comes only from the verified JWT; headers such as `X-Role` are ignored.
- Reference: SD Elements guidance for T85.

**Success Criteria:**
- [ ] Replay tests for all privileged actions return 403 for unpermitted roles.
- [ ] Direct Supabase writes from unpermitted roles affect zero rows.
- [ ] Manual proxy test on a preview deployment recorded as passed.

**Status:** Pending
