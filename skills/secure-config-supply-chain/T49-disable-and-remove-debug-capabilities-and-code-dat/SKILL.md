---
name: t49-disable-and-remove-debug-capabilities-and-code-dat
description: Ship ACME Clinical to Vercel with a secure out-of-the-box configuration - FastAPI docs/OpenAPI and debug off, no test backdoors or demo shortcuts in production, no source maps or verbose server headers - with all security controls enabled by default.
---

# T49: Disable and remove debug capabilities and code/data, and prepare application for release

**Category:** CODE_FIX
**SD Elements:** [T49](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T49/)
**Priority:** 7/10 · **Phase:** requirements

**Spec Context:**
> "README com os passos para rodar e publicar a versão web e a API na Vercel. Confira os fluxos"
> "principais, mantenha a implementação objetiva e conclua as páginas e ações descritas."
> (EN: README with the steps to run and publish the web version and the API on Vercel. Check the main flows, keep the implementation objective and complete the described pages and actions.)
> Source: specs/PRD.md, lines 49-51

**What the spec implies (naive approach):**
"Check the main flows" leads to debug aids that stay in the release: `/docs` and `/openapi.json` enabled, `debug=True` stack traces, a `X-Debug-Role` header or `/dev/login-as` route used during testing, Vite source maps published, `console.log` of API responses, and the simulation reset open to everyone.

**Secure Implementation Pattern:**
```python
# backend/app/main.py
settings = get_settings()                     # app_env defaults to "production"
app = FastAPI(
    title="ACME Clinical API",
    docs_url="/docs" if settings.docs_enabled else None,      # never in production
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    debug=False,
)
assert_routes_protected(app, production=settings.is_production)   # no unauthenticated leftovers

# backend/app/core/config.py
@property
def docs_enabled(self) -> bool:
    return self.app_env == "development" or (self.enable_docs and not self.is_production)
```
```ts
// frontend/vite.config.ts
export default defineConfig({ build: { sourcemap: false }, esbuild: { drop: ["console", "debugger"] } });
```

**Implementation Guidance:**
- Production is the default (`app_env = "production"` in `backend/app/core/config.py`); docs, OpenAPI and debug are off unless `APP_ENV=development`; production log level is INFO (`backend/app/core/logging.py`).
- No test-only routes, impersonation headers or hard-coded bypasses in `backend/app/routers/*`; test fixtures live only under `backend/tests/` and are excluded from the Vercel bundle (`backend/vercel.json` / `.vercelignore`).
- The demo CLI (`backend/app/cli.py`) refuses to create demo accounts in production; simulation reset stays admin-only with typed confirmation.
- Frontend release build: no source maps, `console`/`debugger` dropped, no dev-only routes (`frontend/vite.config.ts`, `frontend/src/App.tsx`).
- Avoid revealing versions: no `Server`/`X-Powered-By` from the app (`backend/app/core/middleware.py`); generic error bodies (`backend/app/core/errors.py`).
- Remove stray files (`.pytest_cache`, `__pycache__`, `*.log`) from deployments via `.gitignore`/`.vercelignore`; document all security features in `docs/security/`.
- Reference: SD Elements guidance for T49.

**Success Criteria:**
- [ ] `backend/tests/test_logging_audit.py::test_t105_production_has_no_debug_surface` and `test_t105_no_debugger_calls_or_reload_in_deploy` pass.
- [ ] `backend/tests/test_secure_config.py::test_t2349_defaults_are_production_with_docs_off_and_no_origins` and `test_t2357_docs_and_openapi_absent_by_default` pass.
- [ ] A frontend build test asserts `dist/` contains no `*.map` files and no `console.log` calls.
- [ ] `curl -I` against the production API shows no `Server`/`X-Powered-By` version details and `/docs` returns 404.

**Status:** Pending
