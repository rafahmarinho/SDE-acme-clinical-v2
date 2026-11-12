---
name: t405-verify-that-broad-paths-and-domains-are-not-set-on
description: Code review and automated tests verifying that no ACME Clinical cookie sets a Domain attribute or a path broader than required, for both FastAPI responses and the deployed Vercel frontend.
---

# T405: Verify that broad paths and domains are not set on session cookies

**Category:** CODE_FIX
**SD Elements:** [T405](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T405/)
**Priority:** 4/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
Testing would focus on whether the two Vercel deployments talk to each other. A cookie widened to a parent domain to "fix" cross-deployment issues would not break any functional test, so it needs an explicit check.

**Secure Implementation Pattern:**
```python
# backend/tests/test_cookies.py
ALLOWED_PATHS = {"__Host-acme_rt": "/", "__Secure-acme_rt": "/api/auth"}

def parse(c: str) -> tuple[str, dict]:
    name = c.split("=", 1)[0]
    attrs = dict((a.split("=", 1) + [""])[:2] for a in (p.strip().lower() for p in c.split(";")[1:]))
    return name, attrs

async def test_cookie_scope(api, demo_credentials):
    resps = [await api.post("/auth/login", json=demo_credentials("admin")), await api.post("/auth/refresh")]
    for r in resps:
        for c in r.headers.get_list("set-cookie"):
            name, attrs = parse(c)
            assert "domain" not in attrs, f"{name} has Domain={attrs['domain']}"
            if name in ALLOWED_PATHS:
                assert attrs.get("path") == ALLOWED_PATHS[name].lower()
```
```bash
# CI static check: no cookie code widens the domain
! grep -rnE "set_cookie\([^)]*domain=|cookieOptions[^}]*domain" backend/app frontend/src
```

**Implementation Guidance:**
- Code review per SD Elements: locate every `set_cookie`/`delete_cookie` in `backend/app` and any cookie helpers in `frontend/src/lib`; confirm no `domain` is set and paths match the documented minimum.
- Add the pytest above to `backend/tests/test_cookies.py` and the grep check to the CI workflow.
- Manual check: in Chrome DevTools > Application > Cookies on the deployed frontend and API hosts, confirm the Domain column shows the exact host (no leading dot) and the Path is `/` only for `__Host-` cookies.
- Reference: SD Elements guidance for T405.

**Success Criteria:**
- [ ] No cookie has a `Domain` attribute or a parent-domain scope.
- [ ] Paths match the documented allow-list.
- [ ] CI grep check and pytest pass.

**Status:** Applied
