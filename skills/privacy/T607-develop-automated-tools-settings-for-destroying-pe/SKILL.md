---
name: t607-develop-automated-tools-settings-for-destroying-pe
description: Implement a configurable retention policy and automated purge job in ACME Clinical so staff profiles, patient records, observations and event history are destroyed or anonymized when no longer needed, managed from an admin settings page.
---

# T607: Develop automated tools/settings for destroying personal information when it is no longer needed

**Category:** CODE_FIX
**SD Elements:** [T607](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T607/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "devem aparecer nas telas e continuar salvos após recarregar a aplicação. Entregue o código"
> (EN: must appear on the screens and remain saved after reloading the application. Deliver the code)
> Source: specs/PRD.md, line 45

**What the spec implies (naive approach):**
The PRD requires persistence and a manual "reiniciar os dados" reset, so a developer will store everything indefinitely and rely on the demo reset as the only deletion path. For real health data there would be no retention schedule, no admin control and no automated destruction, and backups/Storage files would keep personal data forever.

**Secure Implementation Pattern:**
```python
# backend/app/services/retention.py
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

class RetentionPolicy(BaseModel):
    category: str                       # e.g. "observations", "staff_profiles"
    keep_days: int = Field(ge=1, le=3650)
    anchor: str = "last_activity_at"    # relative schedule, not created_at
    action: str = Field(pattern="^(delete|anonymize)$")

async def run_purge(db, storage, now: datetime) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for p in await db.fetch("select * from retention_policies where enabled"):
        pol = RetentionPolicy(**p)
        cutoff = now - timedelta(days=pol.keep_days)
        table = ALLOWED_TABLES[pol.category]          # allow-list, no SQL injection
        rows = await db.fetch(
            f"select id from {table} where {pol.anchor} < $1 and not legal_hold", cutoff)
        ids = [r["id"] for r in rows]
        if pol.action == "anonymize":
            await db.execute(f"update {table} set full_name=null, email=null, "
                             "notes=null where id = any($1)", ids)
        else:
            await storage.remove_prefixes([f"{pol.category}/{i}/" for i in ids])
            await db.execute(f"delete from {table} where id = any($1)", ids)
        deleted[pol.category] = len(ids)
    await db.execute("insert into purge_log(run_at, counts) values ($1, $2)", now, deleted)
    return deleted
```

**Implementation Guidance:**
- Use the data inventory from T313 (`docs/security/data-classification.md`) to list every personal-data table (`profiles`, `patients`, `observations`, `alarm_events`, `audit_events`) and Storage bucket, with a retention period anchored to last activity/discharge/deactivation.
- Add `retention_policies`, `purge_log` and a `legal_hold boolean` column to restricted tables in `supabase/migrations/0001_schema.sql`; RLS so only administrators can read/write policies.
- Add admin endpoints in `backend/app/routers/settings.py` (GET/PUT `/admin/retention`) and a section on the settings screen in `frontend/src/screens/` (part of the unified security settings, T371).
- Schedule `run_purge` via a Vercel Cron job in `backend/vercel.json` calling a protected endpoint (shared secret from env var `CRON_SECRET`).
- Exclude rows flagged as restricted/legal hold; anonymized data may be kept (T545).
- Document how Supabase backups/PITR age out deleted data; there are no external recipients because integrations are simulated.
- Reference: SD Elements guidance for T607.

**Success Criteria:**
- [ ] Administrators can view and change retention periods per category; non-admins get 403.
- [ ] Scheduled purge deletes/anonymizes expired rows and Storage objects, skipping legal-hold rows.
- [ ] Each run writes a `purge_log` row with counts only.
- [ ] Tests in `backend/tests/test_retention_purge.py` (see T735) cover delete, anonymize and legal-hold paths.

**Status:** Applied
