---
name: t2361-design-a-secure-application-architecture-for-the-c
description: Second part of ACME Clinical's cloud architecture design - network and resilience aspects - restricting cross-layer traffic (CORS, CSP connect-src, Supabase network restrictions), Realtime authorization, rate limiting and redundancy on Vercel and Supabase.
---

# T2361: Design a secure application architecture for the cloud environment (Cloud) (2/2)

**Category:** CODE_FIX
**SD Elements:** [T2361](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T2361/)
**Priority:** 10/10 · **Phase:** architecture-design

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current and stable versions of the technologies and Supabase for PostgreSQL, email and)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
Live monitoring over Supabase Realtime is usually built with open broadcast channels, CORS `*` on the API and no rate limits, so any client can subscribe to every patient's vitals or flood the simulation endpoints. This complements T2288 (layer separation) with the controls between and around the layers.

**Secure Implementation Pattern:**
```sql
-- supabase/migrations/0001_schema.sql : Realtime authorization (private channels)
alter table realtime.messages enable row level security;

create policy "clinical staff receive ward vitals"
on realtime.messages for select to authenticated
using (
  realtime.topic() like 'ward:%'
  and exists (
    select 1 from public.staff_ward_access a
    where a.user_id = auth.uid()
      and 'ward:' || a.ward_id::text = realtime.topic()
  )
);
```

```python
# backend/app/main.py -- simple per-user rate limit on mutating simulation endpoints
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
```

**Implementation Guidance:**
- Use private Realtime channels per ward with RLS on `realtime.messages`; the backend broadcasts via the service role, clients only subscribe.
- Restrict cross-layer traffic: API CORS allow-list = frontend production domain; frontend CSP `connect-src` limited to the API and Supabase project; enable Supabase network restrictions / SSL enforcement for direct DB connections.
- Rate-limit authentication-adjacent and simulation endpoints (`backend/app/routers/simulation.py`); enable Vercel Firewall rules for abusive traffic.
- Redundancy: rely on Vercel's multi-region CDN for static assets; document Supabase region, backup schedule and PITR; consider a read replica for reports if load grows.
- Document data flows and controls in `docs/architecture.md`.
- Reference: SD Elements guidance for T2361.

**Success Criteria:**
- [ ] A user without ward access cannot subscribe to that ward's Realtime topic (test).
- [ ] API CORS and frontend CSP restrict origins to known layers.
- [ ] Rate limits return 429 when exceeded (pytest).
- [ ] Redundancy and backup strategy documented.

**Status:** Applied
