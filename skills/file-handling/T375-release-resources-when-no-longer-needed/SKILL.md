---
name: t375-release-resources-when-no-longer-needed
description: Ensures ACME Clinical releases files, temp directories, database connections, HTTP clients and Supabase Realtime subscriptions deterministically using context managers, FastAPI lifespan and React effect cleanups.
---

# T375: Release resources when no longer needed

**Category:** CODE_FIX
**SD Elements:** [T375](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T375/)
**Priority:** 6/10 · **Phase:** development

**Spec Context:**
> "visão por ala, lista e detalhe de pacientes, monitoramento ao vivo, alarmes, dispositivos,"
> (EN: ward view, patient list and detail, live monitoring, alarms, devices,)
> Source: specs/PRD.md, line 25

> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: password, files and real-time updates. I want the screens working and the data)
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
Opening a new DB connection per request without closing it, leaving report files open, and subscribing to Supabase Realtime channels in React components without unsubscribing. Under live monitoring of 10 monitors this exhausts Postgres connections and Realtime quotas and leaks memory in the browser.

**Secure Implementation Pattern:**
```python
# backend/app/db.py
from contextlib import asynccontextmanager
import httpx, psycopg_pool
from fastapi import FastAPI, Request
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = psycopg_pool.AsyncConnectionPool(settings.database_url, min_size=0,
                                                      max_size=5, open=False)
    await app.state.pool.open()
    app.state.http = httpx.AsyncClient(timeout=10)
    try:
        yield
    finally:
        await app.state.http.aclose()
        await app.state.pool.close()

async def get_db(request: Request):
    async with request.app.state.pool.connection() as conn:   # returned to pool on exit
        yield conn
```
```typescript
// frontend/src/hooks/useLiveReadings.ts
useEffect(() => {
  const channel = supabase.channel(`monitor:${monitorId}`)
    .on("postgres_changes", { event: "INSERT", schema: "public", table: "readings",
         filter: `monitor_id=eq.${monitorId}` }, (p) => setReading(p.new as Reading))
    .subscribe();
  return () => { void supabase.removeChannel(channel); };   // release on unmount/change
}, [monitorId]);
```

**Implementation Guidance:**
- Backend: create the DB pool and shared HTTP clients in a FastAPI `lifespan` (`main.py`/`db.py`), hand out connections with `async with` dependencies; for Vercel serverless, use Supabase's pooled connection string (transaction mode) and small pool sizes.
- Files: always use `with open(...)`, `tempfile.TemporaryDirectory()`, `UploadFile.close()` (or `await file.close()`), and delete temp dirs after use (T157); close Pillow images (`with Image.open(...)`).
- Simulation (`services/simulation.py`): stop any background tasks/timers on reset or scenario change.
- Frontend: every Realtime subscription, interval (ECG trace animation), `requestAnimationFrame` and Three.js scene (3D view) must be disposed in the `useEffect` cleanup (`renderer.dispose()`, geometries/materials `.dispose()`).
- Reference: SD Elements guidance for T375.

**Success Criteria:**
- [ ] No connection/file opened outside a context manager (code review / ruff rule `SIM115`).
- [ ] Load test of 500 requests keeps Postgres connections ≤ pool max.
- [ ] Vitest: unmounting live monitoring components calls `removeChannel` and clears intervals.

**Status:** Pending
