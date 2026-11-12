---
name: t2290-secure-data-in-transit-cloud-1-2
description: Enforce TLS for all ACME Clinical traffic (browser to Vercel, Vercel API to Supabase, Realtime websockets, direct Postgres), use secure protocol versions, and keep certificates and secrets stored and rotated securely. Part 1/2 of a shared countermeasure.
---

# T2290: Secure data in transit (Cloud) (1/2) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2290](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2290/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Enforce encrypted protocols such as TLS, use secure protocol versions, store secret keys and certificates securely, and rotate them regularly without letting certificates expire.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.) and line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.))
- Found: Vercel terminates TLS for the frontend and API (automatic certificates, TLS 1.2/1.3); Supabase terminates TLS for its HTTPS, websocket (Realtime) and Postgres endpoints.
- Missing: TLS termination, cipher suites and certificate issuance/renewal are not controlled by application code.
- Conclusion: Platform-managed. Repo-expressible parts: HSTS and other headers in `vercel.json`, `https://`/`wss://` URLs and `sslmode=verify-full` in `.env.example` files, and enabling Supabase SSL enforcement.

**Recommended Action:**
T2290 and T2365 have identical guidance; track together. This file is the master checklist.
- Vercel: custom domains use Vercel-managed certificates (auto-renewed) or uploaded certificates with tracked expiry; HTTP redirects to HTTPS automatically. Add `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` via `headers` in `frontend/vercel.json` and `backend/vercel.json`.
- Supabase: enable SSL Enforcement (Database settings) so Postgres rejects non-TLS connections; if the API connects directly, use `sslmode=verify-full` with the Supabase CA certificate (downloadable from the dashboard) in the connection string documented in `backend/.env.example`.
- Clients: `VITE_SUPABASE_URL` and the API base URL in `frontend/.env.example` are `https://`; Realtime uses `wss://` (supabase-js default).
- Secrets/keys: Supabase secret/service-role key and DB password stored only as Vercel Sensitive environment variables scoped to the API project's Production (and a separate value for Preview); never in Git. Enable the Vercel team policy that enforces Sensitive env vars if available.
- Rotation: rotate the Supabase DB password and API secret keys on a schedule (e.g. every 90 days) and on staff departure or exposure; migrate to Supabase's new publishable/secret keys and asymmetric JWT signing keys to allow rotation without downtime; track uploaded certificate expiry with an alert 30 days ahead.

**Status:** Documented
