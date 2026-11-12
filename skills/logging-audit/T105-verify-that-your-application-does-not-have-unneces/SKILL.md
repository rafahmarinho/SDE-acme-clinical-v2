---
name: t105-verify-that-your-application-does-not-have-unneces
description: Tests that ACME Clinical's production FastAPI and Vite builds on Vercel have no debug mode, open API docs, debug parameters, source maps, test routes or debug headers, and that demo/simulation controls are role-protected.
---

# T105: Verify that your application does not have unnecessary debug capability or leftover test/debug code

**Category:** CODE_FIX
**SD Elements:** [T105](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T105/)
**Priority:** 7/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript in the frontend, published separately on Vercel. Use pnpm in the)
> Source: specs/PRD.md, line 19

> "Prepare dados de demonstração com doze pacientes e dez monitores. Inclua uma área para"
> (EN: Prepare demo data with twelve patients and ten monitors. Include an area to)
> Source: specs/PRD.md, line 41

**What the spec implies (naive approach):**
The FastAPI default exposes `/docs`, `/redoc` and `/openapi.json`; `debug=True` may be left on; Vite builds may ship source maps; and the simulation/reset area may be reachable by anyone. Test helper routes and demo credentials may be deployed.

**Secure Implementation Pattern:**
```python
# backend/app/main.py (control under test)
from fastapi import FastAPI
from app.core.config import settings
prod = settings.app_env == "production"
app = FastAPI(debug=False, docs_url=None if prod else "/docs",
              redoc_url=None, openapi_url=None if prod else "/openapi.json")
```
```python
# backend/tests/test_no_debug.py
import pytest, importlib
from httpx import ASGITransport, AsyncClient

@pytest.mark.asyncio
async def test_production_has_no_debug_surface(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    import app.core.config as cfg; importlib.reload(cfg)
    import app.main as m; importlib.reload(m)
    assert m.app.debug is False
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://t") as c:
        for path in ["/docs", "/redoc", "/openapi.json", "/__test_boom", "/debug"]:
            assert (await c.get(path)).status_code == 404
        r = await c.get("/health?debug=true")
        assert not {"server", "x-debug", "x-powered-by"} & {h.lower() for h in r.headers}
        assert (await c.post("/simulation/reset")).status_code == 401
```

**Implementation Guidance:**
- Backend: assert `debug=False`, docs/OpenAPI disabled in production, no `print()` / `pdb` / `breakpoint()`, no routes registered only for tests in production builds, uvicorn `--reload` not used in `vercel.json`.
- Frontend: `vite.config.ts` `build.sourcemap: false` for production; grep the `dist/` bundle for `console.log`, `debugger`, `localhost`, `SUPABASE_SERVICE_ROLE` and demo passwords; only `VITE_` public vars may be embedded.
- Demo data (`supabase/seed.sql`): 12 fictional patients/10 monitors are intended, but no default admin password in production; the simulation area (scenarios/advance/reset) is admin-only and audited.
- Deployment package: check `backend/tests`, `.env*` (except `.env.example`), fixtures are excluded (`.vercelignore`).
- Manually browse the deployed apps with DevTools, trigger errors, inspect headers.
- Reference: SD Elements guidance for T105.

**Success Criteria:**
- [ ] `backend/tests/test_no_debug.py` passes with `APP_ENV=production`.
- [ ] CI step greps the frontend production bundle and fails on `debugger`/source maps/secrets.
- [ ] Manual check of deployed Vercel apps documented with no debug data found.

**Status:** Pending
