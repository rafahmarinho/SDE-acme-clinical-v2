---
name: t241-verify-that-third-party-libraries-use-secure-setti
description: Test recipe verifying ACME Clinical's Python (FastAPI, Pydantic, supabase-py, httpx) and pnpm (React, Vite, supabase-js, 3D libs) dependencies are patched, lockfile-pinned, audited in CI and configured with secure settings.
---

# T241: Verify that third party libraries use secure settings and the latest patches

**Category:** CODE_FIX
**SD Elements:** [T241](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T241/)
**Priority:** 10/10 · **Phase:** testing

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current and stable versions of the technologies and Supabase for PostgreSQL, email and)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
"Current and stable versions" is satisfied once at scaffold time, then dependencies drift. Unpinned `requirements.txt` ranges and no audit step mean known CVEs ship unnoticed, and libraries are left with insecure settings (Supabase client persisting sessions in localStorage, Vite dev server exposed, FastAPI debug).

**Secure Implementation Pattern:**
```yaml
# .github/workflows/dependency-audit.yml
name: dependency-audit
on: [push, pull_request, { schedule: [{ cron: "0 6 * * 1" }] }]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install pip-audit && pip-audit -r backend/requirements.txt --strict
  node:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm --dir frontend install --frozen-lockfile
      - run: pnpm --dir frontend audit --audit-level=moderate
```

**Implementation Guidance:**
- Generate the inventory: `pip freeze`/`uv pip compile` output for `backend/requirements.txt` (hash-pinned) and `frontend/pnpm-lock.yaml`; produce an SBOM (`cyclonedx-py`, `pnpm sbom` or `cdxgen`).
- Run `pip-audit` and `pnpm audit` in CI (above); the build fails on unresolved advisories without documented workarounds.
- Enable Dependabot (`.github/dependabot.yml`) for `pip` (backend), `npm` (frontend) and `github-actions`.
- Review secure settings per vendor docs: supabase-js auth options, Vite `server.host` only in dev, FastAPI production settings (T2349), PostgreSQL via Supabase advisors.
- Record exceptions with justification in `docs/security/dependencies.md`.
- Reference: SD Elements guidance for T241.

**Success Criteria:**
- [ ] `pip-audit` and `pnpm audit` pass in CI with no unresolved high/critical advisories.
- [ ] Lockfiles committed; `--frozen-lockfile` used in CI and Vercel builds.
- [ ] Dependabot configured for all ecosystems.
- [ ] Library security settings reviewed and documented.

**Status:** Pending
