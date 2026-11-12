---
name: t1881-mitigate-the-risk-of-uncontrolled-data-harvesting
description: Mitigate bot-driven scraping of ACME Clinical patient lists, search and reports using Vercel Firewall bot protection (managed bot rules, BotID, rate limiting, Attack Challenge Mode) and Supabase Auth CAPTCHA, without degrading clinician experience.
---

# T1881: Mitigate the risk of uncontrolled data harvesting (NON-CODE)

**Category:** INFRA
**SD Elements:** [T1881](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T1881/)
**Priority:** 4/10 · **Phase:** requirements

**Guidance:** Deploy technologies that detect sophisticated, human-mimicking scraping bots (behavioural/ML detection), do not rely on a WAF alone, avoid harming real users, and use easy CAPTCHAs when suspicious activity is detected.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 11 "serviços e acesso ao banco. Inclua login, recuperação de senha, perfil, configurações, busca," (EN: services and database access. Include login, password recovery, profile, settings, search,) and line 19 "...publicados separadamente na Vercel." (EN: ...published separately on Vercel.))
- Found: Search, filters, patient lists and reports are exposed via the Vercel-hosted API and Supabase Data API; login/recovery via Supabase Auth.
- Missing: Behavioural bot detection is an edge/platform service (Vercel Firewall/BotID) and a Supabase Auth setting, not something to build in app code.
- Conclusion: Platform control, with small repo-side pieces (BotID client/server check, CAPTCHA token pass-through, `supabase/config.toml` `[auth.captcha]`).

**Recommended Action:**
- Vercel Firewall: enable the managed bot protection ruleset (challenge non-browser automation) and the AI bots ruleset on both projects; add rate-limit rules on list/search/report endpoints (e.g. per IP and per JWT subject); keep Attack Challenge Mode in the incident runbook.
- Vercel BotID: protect high-value API routes (patient search, report generation/export) with BotID verification (invisible challenge, no user friction).
- Supabase Auth: enable CAPTCHA (hCaptcha or Cloudflare Turnstile) for sign-in, sign-up and password recovery; tune Auth rate limits.
- Data API exposure: because all data requires authentication (no public pages), require auth on every table via RLS and cap page sizes (`max_rows` in Supabase API settings), limiting what an authenticated scraper can pull per request.
- Monitoring: alert on a single user/IP enumerating many patient IDs or exporting many reports (see T2294).
- Requirement note: real users are clinicians on shared workstations; prefer invisible challenges and only escalate to CAPTCHA on anomaly.

**Status:** Documented
