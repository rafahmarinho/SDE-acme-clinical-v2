---
name: t379-provide-sufficient-documentation-for-security-rela
description: Write ACME Clinical security documentation (README security section and docs/security/) covering roles and auth, data handled, data protection, secrets, logging/audit, backup/restore, reset/sanitization, insecure demo settings and in-app warnings.
---

# T379: Provide sufficient documentation for security-related features

**Category:** CODE_FIX
**SD Elements:** [T379](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T379/)
**Priority:** 4/10 · **Phase:** requirements

**Spec Context:**
> "README com os passos para rodar e publicar a versão web e a API na Vercel. Confira os fluxos"
> (EN: README with the steps to run and publish the web version and the API on Vercel. Check the main)
> Source: specs/PRD.md, line 49

**What the spec implies (naive approach):**
The README will cover install and deploy steps only. Operators will not know which env vars are secret, what the four roles can do, that the simulation reset wipes data, or which demo settings are insecure for real patient data.

**Secure Implementation Pattern:**
```markdown
<!-- README.md (security section outline) -->
## Security
- Roles & access: nurse, physician, biomedical technician, administrator -> see docs/security/roles.md
- Authentication: Supabase Auth email/password, password recovery, session timeout (SESSION_IDLE_MINUTES)
- Data handled: see docs/security/data-classification.md (staff PII, patient PHI)
- Data protection: TLS in transit (Vercel/Supabase), encryption at rest (Supabase), RLS on all tables
- Secrets: set only in Vercel env vars; SUPABASE_SERVICE_ROLE_KEY is backend-only
- Logging & audit: audit_events table; logs exclude personal data
- Backup/restore: Supabase daily backups / PITR; restore runbook in docs/runbook.md
- Data sanitization: retention purge, account deletion, simulation reset
- Insecure demo settings (turn OFF for real data): ALLOW_SIMULATION_RESET, ENABLE_DOCS, seeded demo accounts
- Reporting vulnerabilities: SECURITY.md
```

```typescript
// frontend/src/components/ConfirmDangerDialog.tsx -- in-product security warning
<ConfirmDangerDialog
  title="Reset all data?"
  message="This permanently deletes all patients, readings, alarms and observations. This cannot be undone."
  confirmLabel="Reset data" requireTyping="RESET" />
```

**Implementation Guidance:**
- Add a Security section to `README.md` and detailed pages in `docs/security/` (roles, data classification, configuration reference from T2349, crypto inventory, dependencies).
- Cover: privacy/data types, authentication/authorization, services/protocols in use (HTTPS, WSS Realtime), data in transit/at rest, emergency procedures (admin break-glass account handling), backup/restore, logging/auditing, device sanitization (how to permanently delete data), and insecure first-run settings (demo seed accounts and passwords must be changed or removed).
- Add in-app warnings for risky actions: simulation reset, staff account deletion, threshold changes.
- Optionally complete an MDS2-style summary since this is a medical device dashboard.
- Reference: SD Elements guidance for T379.

**Success Criteria:**
- [ ] README links to all `docs/security/` pages and lists insecure demo defaults.
- [ ] Documentation covers each topic listed in the guidance.
- [ ] Risky actions show confirmation warnings in the UI (vitest test for reset dialog).
- [ ] `SECURITY.md` describes vulnerability reporting.

**Status:** Pending
