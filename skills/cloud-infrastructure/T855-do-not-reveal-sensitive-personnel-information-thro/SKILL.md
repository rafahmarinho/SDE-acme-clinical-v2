---
name: t855-do-not-reveal-sensitive-personnel-information-thro
description: Ensure the WHOIS records for ACME Clinical's custom domains (frontend and API on Vercel) use registrar privacy or role-based organizational contacts instead of individual staff names, phone numbers and emails.
---

# T855: Do not reveal sensitive personnel information through WHOIS Domain information (NON-CODE)

**Category:** INFRA
**SD Elements:** [T855](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T855/)
**Priority:** 5/10 · **Phase:** deployment

**Guidance:** Make sure WHOIS registration data does not reveal personnel information that could enable social engineering, war dialing or brute force against usernames.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: The web app and API are published on Vercel; custom domains may be bought through Vercel Domains or another registrar.
- Missing: Domain registration contacts are registrar settings.
- Conclusion: Organization IT/registrar control. If only `*.vercel.app` hostnames are used, WHOIS is Vercel's and this CM is satisfied by default.

**Recommended Action:**
- Use registrar WHOIS privacy/redaction (Vercel Domains and most registrars provide it where the TLD allows).
- Where contacts must be public, use role-based entries: organization name, `hostmaster@`/`security@` distribution lists and a switchboard number, never an individual's name, direct phone or an email matching a login username.
- Ensure email addresses used for Vercel/Supabase admin accounts and Supabase Auth admin users do not appear in WHOIS or DNS TXT records.
- Publish a `security.txt` (`/.well-known/security.txt` in `frontend/public/`) with a role address for vulnerability reports instead.
- Review WHOIS output (`whois <domain>`) at registration and at each renewal.

**Status:** Documented
