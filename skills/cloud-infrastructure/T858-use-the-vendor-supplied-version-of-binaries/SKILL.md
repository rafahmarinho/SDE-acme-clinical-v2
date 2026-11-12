---
name: t858-use-the-vendor-supplied-version-of-binaries
description: Use vendor-supplied, maintained runtimes and packages for ACME Clinical (Vercel's managed Python and Node.js runtimes, Supabase-managed Postgres, official Supabase CLI and packages from PyPI/npm via lockfiles) instead of custom-built server binaries.
---

# T858: Use the vendor supplied version of binaries (NON-CODE)

**Category:** INFRA
**SD Elements:** [T858](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T858/)
**Priority:** 4/10 · **Phase:** deployment

**Guidance:** Install servers from vendor-provided binaries to simplify maintenance and receive security patches effectively.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias..." (EN: Use current, stable technology versions...) and line 19 "...publicados separadamente na Vercel. Use pnpm no" (EN: ...published separately on Vercel. Use pnpm on the...))
- Found: The PRD already requires current, stable versions. Server binaries (web runtime, Postgres) are supplied and patched by Vercel and Supabase.
- Missing: No server installation step exists for the team.
- Conclusion: Provider-managed; the customer-side part (choosing official runtimes and packages) is expressed in repo config: runtime pins, lockfiles, CI tooling versions.

**Recommended Action:**
- Use Vercel's built-in Python runtime and Node.js build image; do not vendor custom-compiled interpreters or `bin/` executables into `backend/` or `frontend/`.
- Install dependencies only from official registries (PyPI, npm) through lockfiles (`pnpm-lock.yaml`, pinned `backend/requirements.txt` with hashes where feasible); enable `pnpm` via Corepack with a pinned `packageManager` field.
- Use the official Supabase CLI release (npm `supabase` package, Homebrew or GitHub releases) at a pinned version in CI; keep Supabase Postgres on Supabase-provided versions and apply offered upgrades.
- Enable Dependabot/Renovate to track vendor patch releases.

**Status:** Documented
