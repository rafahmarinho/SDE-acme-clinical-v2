---
name: t10-use-server-to-server-authentication
description: Authenticates every server-to-server hop in ACME Clinical (React to FastAPI with verified Supabase JWTs, FastAPI to Supabase with the server-only service role key over TLS, Vercel Cron to internal endpoints with a shared secret), adapting X.509 mutual TLS, which Vercel serverless does not offer, to signed tokens.
---

# T10: Use server-to-server authentication

**Category:** CODE_FIX
**SD Elements:** [T10](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T10/)
**Priority:** 6/10 · **Phase:** requirements

**Spec Context:**
> "Use Python com FastAPI e Pydantic no backend e React com Vite e TypeScript no frontend, publicados separadamente na Vercel."
> (EN: Use Python with FastAPI and Pydantic on the backend and React with Vite and TypeScript on the frontend, published separately on Vercel.)
> Source: specs/PRD.md, lines 17-19

**What the spec implies (naive approach):**
With separate frontend and API deployments, a developer might trust a `user_id` sent by the frontend, decode JWTs without verifying the signature, or put the service role key in a `VITE_` variable so the browser can "talk to Supabase as admin". Any of these lets anyone call the API or the database with full rights.

**Secure Implementation Pattern:**
```python
# backend/app/core/security.py
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings

_jwks = jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json", cache_keys=True)
_bearer = HTTPBearer(auto_error=False)

def verify_supabase_jwt(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if cred is None:
        raise HTTPException(401, "Authentication failed")
    try:
        key = _jwks.get_signing_key_from_jwt(cred.credentials).key
        return jwt.decode(cred.credentials, key, algorithms=["ES256", "RS256"],
                          audience="authenticated",
                          issuer=f"{settings.supabase_url}/auth/v1",
                          options={"require": ["exp", "sub", "aud", "iss"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Authentication failed")
```
```python
# backend/app/db.py - outbound: backend -> Supabase authenticated with server-only key over HTTPS
from supabase import acreate_client
async def admin_client():
    assert settings.supabase_url.startswith("https://") or settings.env == "local"
    return await acreate_client(settings.supabase_url,
                                settings.supabase_service_role_key.get_secret_value())
```

**Implementation Guidance:**
- Inbound user calls (frontend to FastAPI): require `Authorization: Bearer <Supabase access token>` on every non-public router through `verify_supabase_jwt`. Use Supabase asymmetric JWT signing keys (JWKS). If the project still uses the legacy HS256 secret, verify with `SUPABASE_JWT_SECRET` and plan migration. Never use `options={"verify_signature": False}`.
- Inbound machine calls (Vercel Cron to `/internal/*`): require `Authorization: Bearer ${CRON_SECRET}`, compared with `hmac.compare_digest`, and throttle failures (T114).
- Outbound (FastAPI to Supabase): use `SUPABASE_SERVICE_ROLE_KEY` (or the new secret API key) only in `backend/app/core/config.py`, held as a Vercel server-side env var. It never appears in `frontend/.env.example` or under a `VITE_` prefix. The frontend gets only the anon/publishable key. Use the Postgres connection string with `sslmode=require` in `backend/app/db.py`.
- Mutual TLS: Vercel serverless functions cannot require client certificates, so signed JWTs and secrets over TLS replace X.509 mTLS. Document this as the chosen equivalent.
- Reference: SD Elements guidance for T10.

**Success Criteria:**
- [ ] Requests without a token, with an expired, forged, wrong-audience or HS256 `alg:none` token, or with an unknown `kid`, get 401 (`backend/tests/test_jwt_verification.py`).
- [ ] A build check confirms that no `SERVICE_ROLE` string or secret key appears in `frontend/dist` or in `frontend/.env.example`.
- [ ] `/internal/*` returns 401 without the cron secret.

**Status:** Applied
