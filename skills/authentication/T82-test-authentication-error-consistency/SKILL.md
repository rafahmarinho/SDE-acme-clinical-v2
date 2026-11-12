---
name: t82-test-authentication-error-consistency
description: Security test verifying that ACME Clinical login and backend auth failures for unknown emails and wrong passwords produce identical responses, cookies and local storage, verifying T8.
---

# T82: Test authentication error consistency

**Category:** CODE_FIX
**SD Elements:** [T82](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T82/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "Inclua login, recuperação de senha, perfil, configurações, busca, filtros, estados de carregamento e mensagens de erro."
> (EN: Include login, password recovery, profile, settings, search, filters, loading states and error messages.)
> Source: specs/PRD.md, lines 11-13

**What the spec implies (naive approach):**
Detailed error messages are a PRD requirement, so it is easy for the login screen to show different text, status codes or stored state for "unknown email" and "wrong password". This test catches that regression.

**Secure Implementation Pattern:**
```python
# backend/tests/integration/test_auth_error_consistency.py
import os, httpx, pytest
URL, ANON = os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"]
KNOWN = os.environ["LOCKOUT_TEST_EMAIL"]

def attempt(email: str) -> httpx.Response:
    return httpx.post(f"{URL}/auth/v1/token?grant_type=password",
                      headers={"apikey": ANON}, json={"email": email, "password": "Wrong-Pass-123"})

@pytest.mark.integration
def test_unknown_vs_wrong_password_identical():
    a, b = attempt("no-such-user@acme.test"), attempt(KNOWN)
    assert a.status_code == b.status_code
    assert a.json().get("error_code") == b.json().get("error_code")
    assert a.json().get("msg") == b.json().get("msg")
    assert sorted(a.cookies.keys()) == sorted(b.cookies.keys())
```
```typescript
// frontend/src/screens/Login.test.tsx (vitest + testing-library)
it('shows identical UI and storage for unknown vs known email', async () => {
  mockSignIn({ code: 'invalid_credentials' }); await submit('ghost@acme.test');
  const first = [screen.getByRole('alert').textContent, JSON.stringify(localStorage)];
  mockSignIn({ code: 'invalid_credentials' }); await submit('nurse@acme.test');
  expect([screen.getByRole('alert').textContent, JSON.stringify(localStorage)]).toEqual(first);
});
```

**Implementation Guidance:**
- Steps 1 to 4: run the integration test against local Supabase and compare status, body and cookies for an invalid email and for a valid email with a wrong password.
- In the UI, compare the alert text, the URL and localStorage/sessionStorage keys (`sb-*-auth-token` must not appear after a failure).
- Repeat for backend endpoints (`POST /me/password` with a wrong current password, staff invite for an existing or new email). Bodies must be uniform.
- Step 5 (personal phrase or image): ACME Clinical has none by design. Record this as N/A, and confirm that CAPTCHA appears on repeated attempts anyway.
- Reference: SD Elements guidance for T82.

**Success Criteria:**
- [ ] The integration test passes: identical status, error code and message, and identical cookie names.
- [ ] The Vitest UI test passes: identical alert text and no session storage after failure.

**Status:** Pending
