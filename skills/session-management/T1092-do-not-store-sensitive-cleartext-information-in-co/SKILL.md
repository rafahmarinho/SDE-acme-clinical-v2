---
name: t1092-do-not-store-sensitive-cleartext-information-in-co
description: Keep patient data, roles and tokens out of ACME Clinical cookies; if any cookie is used it holds only an opaque identifier (for example a Supabase refresh token in an HttpOnly cookie), with all user and clinical state kept server-side in Supabase.
---

# T1092: Do not store sensitive cleartext information in cookies

**Category:** CODE_FIX
**SD Elements:** [T1092](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T1092/)
**Priority:** 4/10 · **Phase:** architecture-design

**Spec Context:**
> "Adapte a navegação aos perfis de"
> "usuário."
> (EN: Adapt the navigation to the user profiles.)
> Source: specs/PRD.md, lines 13-15

> "Use pacientes fictícios e monitores simulados para mostrar"
> (EN: Use fictional patients and simulated monitors to show)
> Source: specs/PRD.md, line 29

**What the spec implies (naive approach):**
To adapt navigation by role and remember the last ward or patient, a developer might write cookies such as `role=administrator`, `ward=ICU-2` or `lastPatient=Maria Silva`, or switch to `@supabase/ssr` cookie storage, which puts the base64 (not encrypted) JWT, including email and role claims, into cookies. Cookies are readable on the device and sent with every request; a client-set role cookie could even be trusted for authorization.

**Secure Implementation Pattern:**
```python
# backend/app/routers/profile.py - role and preferences come from the server, never from cookies
class MeOut(BaseModel):
    display_name: str
    role: Literal["nurse", "physician", "biomedical_technician", "administrator"]
    default_ward_id: int | None

@router.get("/me", response_model=MeOut)
async def me(sess: Session = Depends(require_session), db=Depends(get_db)):
    return await load_profile(db, sess.user_id)      # role from staff table (checked by RLS)

# The only cookie the API may set (optional BFF): opaque, HttpOnly, no PII
def set_refresh_cookie(resp: Response, opaque_refresh_token: str) -> None:
    resp.set_cookie("__Host-acme_rt", opaque_refresh_token, httponly=True,
                    secure=True, samesite="strict", path="/")
# Forbidden: resp.set_cookie("role", ...), resp.set_cookie("patient", ...), JWT in a cookie
```

**Implementation Guidance:**
- Navigation by role: the SPA calls `GET /me` and keeps the result in memory; authorization is enforced by FastAPI dependencies and Supabase RLS from the `staff` table, never from client-held values.
- UI preferences (last ward, filters, theme) are stored server-side in a `user_preferences` table, or in `localStorage` only if they contain no patient identifiers; never in cookies.
- Do not use `@supabase/ssr` cookie storage in the SPA; the JWT payload is merely base64url-encoded and would expose email and role in cookies.
- Do not add PII or clinical data to custom JWT claims (Supabase custom access token hook); keep claims to `sub`, `role`, `session_id`, and an app role identifier.
- If a client-side value must ever be stored in a cookie, encrypt and sign it (for example `cryptography.fernet` with a key from Vercel environment variables), verify the signature before decrypting, and discard it on failure. Prefer the server-side session (`app_sessions`) instead.
- Reference: SD Elements guidance for T1092.

**Success Criteria:**
- [ ] No cookie contains patient names, ward/bed identifiers, email, role or a JWT.
- [ ] Any session cookie is an opaque token, HttpOnly, Secure, SameSite=Strict.
- [ ] Changing any cookie value cannot change the user's role or visible data (server-side authorization only).
- [ ] Verified by T1093.

**Status:** Applied
