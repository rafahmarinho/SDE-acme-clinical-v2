---
name: t349-protect-audit-information-and-logs-against-unautho
description: Protect ACME Clinical audit data (public.events, system_alerts, audit settings and reports, Vercel function logs) against unauthorized reading, modification and deletion with append-only grants, hash chaining, signatures, admin-only read access and a preserved trail across simulation resets.
---

# T349: Protect audit information and logs against unauthorized access

**Category:** CODE_FIX
**SD Elements:** [T349](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T349/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "Prepare dados de demonstração com doze pacientes e dez monitores. Inclua uma área para"
> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: Prepare demo data with twelve patients and ten monitors. Include an area to choose scenarios, advance the simulation, view events and reset the data. The results)
> Source: specs/PRD.md, lines 41-43

**What the spec implies (naive approach):**
"View events and reset the data" suggests one `events` table that every role can read and that `reset` truncates along with the demo data. Anyone with API or database access could then edit or delete the record of who acknowledged which alarm, and a reset would silently wipe the audit trail.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql / 0002_roles_rls.sql
grant insert on public.events to acme_api;                 -- append only: no update/delete/truncate
create trigger events_no_update before update or delete on public.events
  for each row execute function public.events_block_mutation();
create trigger events_no_truncate before truncate on public.events
  for each statement execute function public.events_block_mutation();
create trigger events_hash_chain before insert on public.events
  for each row execute function public.events_hash_chain();   -- prev_hash -> row_hash
create policy events_read on public.events for select to acme_api
  using (public.current_staff_role() = 'admin' or actor_id = public.current_staff_id());
```
```python
# backend/app/routers/events.py - read-only, admin-only integrity check (chain + signatures)
@router.get("/integrity", response_model=IntegrityOut)
async def verify_integrity(request: Request, principal: Admin, limit: int = SIGNATURE_SAMPLE) -> dict:
    async with transaction(principal) as conn:
        chain = await fetch_one(conn, "select public.verify_event_chain() as broken_at")
        rows = await fetch_all(conn, "select ... from public.events order by id desc limit %s", (limit,))
    invalid = sorted(r["id"] for r in rows if r.get("signature") and not verify_row(r))
    return {"intact": chain["broken_at"] is None and not invalid, ...}
```

**Implementation Guidance:**
- Audit data = `public.events` rows, `public.system_alerts`, audit settings in `public.security_settings`, and generated audit reports; classify them in `docs/security/data-classification.md`.
- Append-only: the API role has `insert` only on `public.events`; `events_block_mutation` (`0001_schema.sql`) blocks update/delete/truncate; `reset_simulation_data()` (`0003_authz_rbac.sql`) never touches `events`.
- Tamper evidence: hash chain (`event_row_hash`, `events_hash_chain`, `verify_event_chain` in `0004_ops_audit_resilience.sql`) plus ECDSA signatures from `backend/app/core/audit.py` / `backend/app/services/integrity.py`; verify on read via `GET /v1/events/integrity`.
- Read access: full event history and the audit report (`GET /v1/reports/audit`) for administrators only; other roles see only their own or ward-scoped clinical events (`backend/app/routers/events.py`). Audit settings changes are themselves audited (T371).
- Application logs: redact before writing (`backend/app/core/logging.py`); Vercel log access restricted to team owners and log drains sent over TLS to a store with retention/immutability (INFRA, see cloud-infrastructure T2293/T2368).
- Old audit data is archived/destroyed only by the documented retention job, never by app users.
- Reference: SD Elements guidance for T349.

**Success Criteria:**
- [ ] `backend/tests/test_logging_audit.py::test_t350_events_append_only_and_reset_preserves_audit` and `test_t350_nurse_cannot_verify_or_read_all_events` pass.
- [ ] `test_t486_tampering_any_signed_field_is_detected` and `test_t486_integrity_endpoint_reports_invalid_signatures` pass.
- [ ] `backend/tests/test_database_policies.py`: `update`/`delete`/`truncate` on `public.events` as `acme_api` fail with a permission error.
- [ ] `test_t438_audit_report_forbidden_for_nurse_and_physician` passes.

**Status:** Applied
