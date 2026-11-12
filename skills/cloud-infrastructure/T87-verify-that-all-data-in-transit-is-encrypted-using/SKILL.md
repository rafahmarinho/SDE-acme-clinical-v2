---
name: t87-verify-that-all-data-in-transit-is-encrypted-using
description: Test that ACME Clinical's login, password recovery and post-login clinical traffic is never sent in clear text and that the Vercel and Supabase TLS endpoints reject SSLv2/v3, NULL/EXPORT/DES ciphers and TLS compression and prefer SHA-2 suites.
---

# T87: Verify that all data in transit is encrypted using a secure TLS channel (NON-CODE)

**Category:** INFRA
**SD Elements:** [T87](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T87/)
**Priority:** 8/10 · **Phase:** testing

**Guidance:** Use a network monitor (e.g. Wireshark) during authentication and post-authentication flows; fail on any clear text. For each TLS endpoint, fail if SSLv1/v2/v3 are negotiable, if NULL, EXPORT or DES ciphers are offered, or if TLS compression is enabled; verify the server prefers SHA384/SHA256 over SHA1 and SHA-2 over MD5 suites.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 11 "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca," (EN: services and database access. Include login, password recovery, profile, settings, search,) and line 19 "...publicados separadamente na Vercel." (EN: ...published separately on Vercel.))
- Found: Login and password recovery go through Supabase Auth over HTTPS; app traffic goes to Vercel (frontend and API) and Supabase (REST, Realtime, Storage).
- Missing: Protocol versions and cipher suites are fixed by Vercel's and Supabase's TLS terminators; the application cannot change them.
- Conclusion: A test of provider endpoints; findings would be raised with the provider. Repo-side contribution is only ensuring every configured URL is `https://`/`wss://`.

**Recommended Action:**
Test procedure (security tester, against a staging deployment with demo data):
- Capture traffic with Wireshark (passive capture, no interception proxy) while doing: login, password recovery request and reset link, profile update, opening live monitoring, acknowledging an alarm, uploading/downloading a file, generating a report. Fail on any HTTP (port 80) payload other than the 301/308 redirect, or any `ws://`.
- For each endpoint (frontend domain, API domain, `<project>.supabase.co` 443, `db.<project>.supabase.co` 5432/6543 with STARTTLS-Postgres): run `testssl.sh --protocols --ciphers --server-preference --compression <host>` (use `--starttls postgres` for the DB).
  - Fail if SSLv2/SSLv3 offered; fail on NULL, EXPORT, anonymous or DES/3DES suites; fail if TLS compression is offered.
  - Confirm server preference selects AEAD/SHA-256/384 suites (TLS 1.3 suites or ECDHE-...-GCM-SHA384/SHA256) over SHA-1 suites.
- Record results; any failure on a provider endpoint is escalated to Vercel/Supabase support, since it is not fixable in the repo.
- Re-run after domain changes and at least yearly.

**Status:** Documented
