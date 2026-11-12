---
name: t599-do-not-rely-on-mutable-http-headers-such-as-host-a
description: Ensures ACME Clinical never builds password-reset/callback links from the Host or X-Forwarded-Host header and never uses Referer for authentication or authorization decisions; uses env-configured base URLs and JWT-based auth instead.
---

# T599: Do not rely on mutable HTTP headers such as 'host' and 'referer'

**Category:** CODE_FIX
**SD Elements:** [T599](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T599/)
**Priority:** 4/10 · **Phase:** development

**Spec Context:**
> "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca,"
> (EN: "services and database access. Include login, password recovery, profile, settings, search,")
> Source: specs/PRD.md, line 11

**What the spec implies (naive approach):**
Password recovery, staff invitations and report links need absolute URLs. A developer may use `request.base_url` / `request.headers["host"]` in FastAPI or `window.location.origin` passed to the API, so a forged Host header (host header poisoning) makes reset emails point to an attacker domain. A Referer check might also be used to "protect" the simulation reset action.

**Secure Implementation Pattern:**
```python
# backend/app/core/config.py
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    frontend_url: AnyHttpUrl            # e.g. https://acme-clinical.vercel.app
    allowed_hosts: list[str] = ["acme-clinical-api.vercel.app"]

settings = Settings()

# backend/app/main.py
from starlette.middleware.trustedhost import TrustedHostMiddleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts + ["localhost", "testserver"])

# backend/app/routers/staff.py
def invite_link(token_ref: str) -> str:
    return f"{str(settings.frontend_url).rstrip('/')}/accept-invite?ref={token_ref}"  # never request.base_url

# Authorization is based on the verified Supabase JWT only - never on Referer/Origin/Host.
@router.post("/simulation/reset")
async def reset(user: User = Depends(require_role("administrator"))):
    ...
```

**Implementation Guidance:**
- Build absolute links (invites, reset redirects, report links) from `FRONTEND_URL`/`VITE_APP_URL` environment variables only.
- Add `TrustedHostMiddleware` with the API's Vercel domains so unexpected Host values are rejected.
- Do not trust `X-Forwarded-Host`/`X-Forwarded-For` beyond Vercel's proxy; use them only for logging, never for links or access decisions.
- Never use `Referer` (or `Origin`) as authentication; authorization relies on Supabase JWT verification in `backend/app/core/security.py` and role checks. CORS origin lists come from config, not from echoing the request header.
- Reference: SD Elements guidance for T599.

**Success Criteria:**
- [ ] Code search finds no `request.base_url`, `request.url_for` for external links, or `headers["host"]`/`referer` in decision logic.
- [ ] Test: request with `Host: evil.example` returns 400; invite/reset links always use the configured frontend URL.
- [ ] Simulation reset without a valid admin JWT is denied regardless of Referer.

**Status:** Applied
