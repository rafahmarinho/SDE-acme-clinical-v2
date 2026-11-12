---
name: t305-verify-that-your-application-dynamically-loads-cod
description: Test recipe verifying ACME Clinical's React/Vite frontend (including any 3D simulation assets) and Python backend load code only from the bundled same-origin build, enforced by CSP, and never from user-controlled or remote URLs.
---

# T305: Verify that your application dynamically loads code only from secure locations

**Category:** CODE_FIX
**SD Elements:** [T305](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T305/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you can create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
A 3D view tempts developers to pull Three.js, loaders or decoder WASM (Draco/Basis) from public CDNs at runtime, or to `import()` modules by URL. The backend may use `importlib` to load scenario plugins by name from a request. Code from unverified or user-influenced locations can then run in the clinician's browser or on the server.

**Secure Implementation Pattern:**
```json
// frontend/vercel.json (excerpt)
{
  "headers": [{
    "source": "/(.*)",
    "headers": [{
      "key": "Content-Security-Policy",
      "value": "default-src 'self'; script-src 'self'; worker-src 'self' blob:; connect-src 'self' https://*.supabase.co wss://*.supabase.co https://<api-project>.vercel.app; object-src 'none'; base-uri 'self'"
    }]
  }]
}
```

```python
# backend/app/services/simulation.py  -- allow-listed scenarios, no dynamic import by name
SCENARIOS = {"normal": normal, "low_spo2": low_spo2, "low_battery": low_battery,
             "sensor_fault": sensor_fault, "connection_loss": connection_loss}

def get_scenario(name: str):
    try:
        return SCENARIOS[name]
    except KeyError:
        raise ValueError("Unknown scenario")
```

**Implementation Guidance:**
- Search: `rg "import\(|new Function|eval\(|<script src=|importScripts|setDecoderPath" frontend/src` and `rg "importlib|__import__|exec\(|eval\(" backend/app`.
- Frontend: install 3D libraries via pnpm and bundle them with Vite; copy decoder WASM into `frontend/public/` and set loader paths to same-origin. Vite `import()` code-splitting with static paths is fine.
- Enforce `script-src 'self'` CSP in `frontend/vercel.json`; add a Playwright/vitest check that the deployed page has the header and no external script tags in `dist/index.html`.
- Backend: map scenario names to functions via an allow-list; never import modules from request data or downloaded files.
- Reference: SD Elements guidance for T305.

**Success Criteria:**
- [ ] No runtime script loads from third-party origins (built `dist/` grep test and CSP header test).
- [ ] CSP `script-src 'self'` deployed on the frontend.
- [ ] No `eval`, `new Function`, or dynamic import from variable URLs in source.
- [ ] Backend scenario selection uses an allow-list; unknown names return 422.

**Status:** Applied
