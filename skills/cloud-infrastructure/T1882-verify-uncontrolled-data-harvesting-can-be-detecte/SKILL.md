---
name: t1882-verify-uncontrolled-data-harvesting-can-be-detecte
description: Run a controlled scraping bot against an ACME Clinical staging deployment to confirm Vercel bot protection, rate limits and Supabase Auth CAPTCHA detect or block it and that alerts fire.
---

# T1882: Verify uncontrolled data harvesting can be detected (NON-CODE)

**Category:** INFRA
**SD Elements:** [T1882](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1882/)
**Priority:** 4/10 · **Phase:** testing

**Guidance:** Use a data harvesting bot against the application; the test fails if the application does not detect it.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 11 "...busca," (EN: ...search,) and line 13 "filtros, estados de carregamento e mensagens de erro." (EN: filters, loading states and error messages.))
- Found: Search/filter/list features on the Vercel-hosted app and API.
- Missing: Detection is provided by Vercel Firewall/BotID and Supabase Auth settings configured per T1881.
- Conclusion: Operational test against platform controls.

**Recommended Action:**
Test procedure (authorized, staging only, demo data, coordinated with Vercel's acceptable-use terms):
- Unauthenticated bot: Playwright/headless Chrome script attempting repeated logins and password-recovery requests; expect CAPTCHA enforcement and Auth rate-limit errors (429).
- Authenticated scraper: script that logs in as a demo nurse and pages through patient list, search and report endpoints at machine speed (with and without randomized delays/realistic headers); expect Firewall rate-limit or bot challenge, BotID rejection on protected routes, and capped page sizes.
- Detection: confirm the activity appears in the Vercel Firewall dashboard and the SIEM alert from T2294 fires within the agreed time.
- Fail if the bot completes a full enumeration of the 12 demo patients' details and reports repeatedly without any block, challenge or alert.

**Status:** Documented
