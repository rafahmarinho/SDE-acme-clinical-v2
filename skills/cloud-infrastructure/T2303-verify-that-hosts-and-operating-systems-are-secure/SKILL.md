---
name: t2303-verify-that-hosts-and-operating-systems-are-secure
description: Verify host/OS security for ACME Clinical by collecting Vercel and Supabase provider assurance and checking the customer-side equivalents (pinned supported runtimes, patched dependencies, scoped function credentials).
---

# T2303: Verify that hosts and operating systems are secure (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2303](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T2303/)
**Priority:** 10/10 · **Phase:** testing

**Guidance:** Verify restricted access to OS images, minimal images, use of OS security features, automated patching, instances from approved images only, and restricted instance permissions.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 19 "React com Vite e TypeScript no frontend, publicados separadamente na Vercel." (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.))
- Found: Serverless Vercel functions and managed Supabase hosts.
- Missing: No customer-visible hosts; verification relies on provider attestations and the T2291 equivalents.
- Conclusion: Manual/operational verification.

**Recommended Action:**
Checklist:
- [ ] Current Vercel and Supabase SOC 2 reports on file and reviewed for host hardening/patching controls.
- [ ] API Python runtime and frontend Node.js version are within the vendor's supported (non-EOL) range.
- [ ] `pip-audit` / `pnpm audit` (or Snyk/Veracode SCA) run in CI with no unresolved critical findings.
- [ ] Supabase Postgres version is current or an upgrade is scheduled.
- [ ] API function env vars reviewed: only required variables present per environment; frontend project holds no server secrets.

**Status:** Documented
