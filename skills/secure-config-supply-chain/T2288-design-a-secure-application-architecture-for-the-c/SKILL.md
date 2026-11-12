---
name: t2288-design-a-secure-application-architecture-for-the-c
description: Design ACME Clinical as separated web (React on Vercel CDN), application (FastAPI on Vercel Functions) and data (Supabase PostgreSQL/Auth/Storage/Realtime) layers, with the browser never holding privileged data-layer credentials.
---

# T2288: Design a secure application architecture for the cloud environment (Cloud) (1/2)

**Category:** CODE_FIX
**SD Elements:** [T2288](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T2288/)
**Priority:** 10/10 · **Phase:** architecture-design

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
The PRD already separates frontend and API deployments, but a common shortcut is to have the React app talk directly to every Supabase table (bypassing the Python business logic for alarms and readings), or to give the API layer the service role key for everything. Layers then exist on paper while the data layer is effectively exposed to the browser.

**Secure Implementation Pattern:**
```json
// backend/vercel.json -- application layer (FastAPI on Vercel Python functions)
{
  "functions": { "api/index.py": { "maxDuration": 30 } },
  "rewrites": [{ "source": "/(.*)", "destination": "/api/index.py" }],
  "regions": ["iad1"],
  "headers": [{ "source": "/(.*)", "headers": [
    { "key": "Strict-Transport-Security", "value": "max-age=63072000; includeSubDomains" },
    { "key": "X-Content-Type-Options", "value": "nosniff" } ] }],
  "crons": [{ "path": "/internal/retention/run", "schedule": "0 3 * * *" }]
}
```

**Implementation Guidance:**
- Web layer: `frontend/` static build on Vercel's CDN (DDoS protection, TLS). Uses only the Supabase anon key for Auth sessions and Realtime subscriptions on RLS-protected channels; all writes (observations, acknowledgements, thresholds, simulation) go through the API.
- Application layer: `backend/` FastAPI on Vercel Functions (autoscaled, load-balanced by the platform). Verifies Supabase JWTs, enforces roles, runs readings/alarms/reports in Python. Uses the user's JWT for RLS-scoped queries and the service role key only for admin/system tasks.
- Data layer: Supabase PostgreSQL (RLS on all tables, no public schema exposure beyond needed views), private Storage buckets, Realtime authorization.
- Co-locate Vercel function region with the Supabase project region; document availability expectations (Supabase backups/PITR, Vercel multi-region CDN).
- Draw the layer diagram and trust boundaries in `docs/architecture.md`.
- Reference: SD Elements guidance for T2288.

**Success Criteria:**
- [ ] Architecture document shows three layers, trust boundaries and which keys each layer holds.
- [ ] Frontend contains no direct table writes to protected tables (code search + RLS denies).
- [ ] Service role key exists only in backend Vercel env.
- [ ] Function region matches the Supabase region.

**Status:** Pending
