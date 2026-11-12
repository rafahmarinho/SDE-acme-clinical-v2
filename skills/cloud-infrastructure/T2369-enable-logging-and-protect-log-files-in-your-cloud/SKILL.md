---
name: t2369-enable-logging-and-protect-log-files-in-your-cloud
description: Enable and protect provider-side logs for ACME Clinical's two Vercel projects (frontend and FastAPI API) through log drains, audit logs and restricted access, with backed-up, sufficiently detailed entries. Part 3/4 of a shared countermeasure.
---

# T2369: Enable logging and protect log files in your cloud environment (Cloud) (3/4) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2369](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2369/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** Use the cloud provider's logging services, enable logging of configuration changes and of every cloud service in use, restrict access to logs, encrypt logs where possible, version and back up logs, and include sufficient information in log entries.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 49 "README com os passos para rodar e publicar a versão web e a API na Vercel." (EN: README with the steps to run and publish the web version and the API on Vercel.))
- Found: The web app and the API are each published as Vercel projects; data services are hosted Supabase. No logging requirements in the PRD.
- Missing: Vercel runtime/build/firewall log retention, log drains and team audit logs are Vercel team settings, not application code.
- Conclusion: Platform control owned by the Vercel team administrators.

**Recommended Action:**
This part shares the same guidance as T2293 (1/4), T2368 (2/4) and T2370 (4/4); track them together and use the T2293 checklist as the master. Suggested evidence slice for this part: the Vercel projects.
- Log Drains: in Team Settings > Log Drains, add a drain for both projects covering runtime (Python function) logs, build logs, static/edge request logs and firewall events; deliver over HTTPS to the organization SIEM and verify the drain signature header on the receiver.
- Audit: use the Vercel Audit Log (Enterprise) or Activity feed to capture env var edits, domain/alias changes, deployment protection changes and member/role changes; export it periodically to the SIEM.
- Access: keep the team small; give clinicians and testers no Vercel access, developers the Developer role, and only named administrators the Owner role.
- Content: ensure `backend/app/core/logging.py` emits structured JSON with `x-vercel-id`, user ID, role, route and status; no tokens, passwords or patient payloads.
- Protection/backup: the SIEM destination must be encrypted, versioned or immutable, and have a documented retention.
- Repo config: drains can be declared with Terraform (`vercel_log_drain`) if the organization manages Vercel as code.

**Status:** Documented
