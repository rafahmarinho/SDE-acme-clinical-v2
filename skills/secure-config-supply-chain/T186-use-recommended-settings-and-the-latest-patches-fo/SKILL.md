---
name: t186-use-recommended-settings-and-the-latest-patches-fo
description: Keep ACME Clinical's third-party components (FastAPI, Pydantic, psycopg, PyJWT, cryptography, React, Vite, supabase-js and the Supabase/Vercel runtimes) on current patched versions with their most secure settings, enforced by pinned dependencies, CI audits and Dependabot.
---

# T186: Use recommended settings and the latest patches for third party libraries and software

**Category:** CODE_FIX
**SD Elements:** [T186](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T186/)
**Priority:** 10/10 · **Phase:** development

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current, stable versions of the technologies and Supabase for PostgreSQL, e-mail login and)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
"Current, stable versions" is satisfied once at project creation with `pip install fastapi` and `pnpm create vite`; ranges like `^` or `>=` then drift, no one audits advisories, and library defaults (FastAPI docs enabled, permissive CORS, Supabase signups open) stay as shipped.

**Secure Implementation Pattern:**
```yaml
# .github/workflows/ci.yml
- name: Audit Python dependencies
  run: pip-audit -r backend/requirements.txt --strict
- name: Audit frontend dependencies
  working-directory: frontend
  run: pnpm install --frozen-lockfile && pnpm audit --audit-level=moderate
```
```yaml
# .github/dependabot.yml
updates:
  - { package-ecosystem: pip,            directory: /backend,  schedule: { interval: weekly } }
  - { package-ecosystem: npm,            directory: /frontend, schedule: { interval: weekly } }
  - { package-ecosystem: github-actions, directory: /,         schedule: { interval: weekly } }
```
```python
# backend/app/main.py - secure framework settings, not defaults
app = FastAPI(docs_url="/docs" if settings.docs_enabled else None, redoc_url=None,
              openapi_url="/openapi.json" if settings.docs_enabled else None, debug=False)
```

**Implementation Guidance:**
- Pin exact versions in `backend/requirements.txt` / `requirements-dev.txt` and `frontend/package.json` + `frontend/pnpm-lock.yaml`; install with `--frozen-lockfile`; document holds (e.g. the FastAPI `<0.137` hold) and their review date in the file header and `docs/security/secure-config.md`.
- CI (`.github/workflows/ci.yml`) fails on known vulnerabilities (`pip-audit --strict`, `pnpm audit`), and Dependabot (`.github/dependabot.yml`) covers pip, npm and GitHub Actions weekly; patch security advisories within an agreed SLA.
- Apply secure settings per component: FastAPI docs/debug off in production (`backend/app/main.py`), PyJWT with explicit `algorithms` (`backend/app/core/security.py`), psycopg with `sslmode=verify-full`, Supabase Auth hardening in `supabase/config.toml` (`enable_signup = false`, `secure_password_change`, rate limits), strict CSP/headers in `frontend/vercel.json`.
- Pin the runtime: Python version for the Vercel function and `engines.node` / `packageManager` in `frontend/package.json`; keep Supabase Postgres on the latest minor via the dashboard (INFRA).
- Keep the component register in `docs/security/secure-config.md` current for each direct dependency.
- Reference: SD Elements guidance for T186.

**Success Criteria:**
- [ ] `backend/tests/test_secure_config.py::test_t241_backend_dependencies_are_exactly_pinned`, `test_t241_frontend_dependencies_are_exact_and_locked` and `test_t241_ci_audits_dependencies_and_dependabot_covers_all_ecosystems` pass.
- [ ] `pip-audit -r backend/requirements.txt --strict` and `pnpm audit --audit-level=moderate` are clean on the release commit.
- [ ] `test_t370_component_register_documents_every_direct_dependency` passes, and no Dependabot security PR stays open longer than the agreed SLA.

**Status:** Applied
