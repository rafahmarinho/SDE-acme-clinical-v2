---
name: t2302-verify-that-data-in-transit-is-secured-cloud
description: Verify that all ACME Clinical traffic to Vercel and Supabase uses current TLS, that keys and certificates are stored securely, and that rotation prevents expired certificates.
---

# T2302: Verify that data in transit is secured (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2302](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2302/)
**Priority:** 10/10 · **Phase:** testing

**Guidance:** Verify use of secure protocols (TLS), secure protocol versions, secure storage of keys and certificates, and a rotation schedule that prevents use of expired certificates.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Provider-terminated TLS on Vercel and Supabase.
- Missing: Verification targets endpoints and settings controlled by providers (see T2290/T2365).
- Conclusion: Operational verification using external scanners.

**Recommended Action:**
Checklist:
- [ ] `testssl.sh` (or SSL Labs) against the frontend domain, API domain and `<project>.supabase.co`: only TLS 1.2/1.3, no weak ciphers, valid chain, grade A or better.
- [ ] `curl -I http://<frontend>` redirects to HTTPS; HTTPS responses carry HSTS.
- [ ] `psql "...?sslmode=disable"` to Supabase is rejected (SSL enforcement on).
- [ ] Browser devtools on live monitoring screen: Realtime uses `wss://`; no mixed-content warnings.
- [ ] Secrets inventory (T2365) shows all secrets in Vercel Sensitive env vars / Supabase, with rotation dates within policy; certificate expiry monitor configured.
- [ ] Repo secret scan (gitleaks) clean.

**Status:** Documented
