---
name: t364-enable-secure-backup-and-restore-capabilities
description: Define ACME Clinical's backup scope (database, Auth users, Storage files, configuration/secrets), protection, transport security and secure-state recovery using Supabase backups/PITR; the in-app data reset is a simulation feature, not a backup.
---

# T364: Enable secure backup and restore capabilities (NON-CODE)

**Category:** INFRA
**SD Elements:** [T364](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T364/)
**Priority:** 6/10 · **Phase:** requirements

**Guidance:** Decide which data types are backed up; protect backups like the original data; choose the backup location, secure the channel with TLS and authenticate the backup server; restore to a secure state after failure (minimum data, system and security parameters, patches); be able to resume or restart failed backups.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 43 "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados" (EN: "choose scenarios, advance the simulation, view events and reset the data"))
- Found: Supabase PostgreSQL, Auth, Storage and Realtime; data must persist across reloads. The data reset is part of the simulation area and restores demo seed data only.
- Missing: the PRD defines no backup requirement; backups are a Supabase platform capability.
- Conclusion: Requirements/ops decision implemented in Supabase settings. Repo inputs to secure-state recovery: `supabase/migrations/` (schema, RLS policies, grants), `.env.example` files (list of required secrets) and the README restore section.

**Recommended Action:** Product/platform owner: (1) document backup scope: Postgres data (Supabase daily backups/PITR), Auth users (in the database), Storage buckets (separate copy), secrets and Vercel/Supabase configuration (vault/IaC notes); (2) require encrypted, access-restricted backups over TLS; (3) define secure-state recovery: re-apply migrations, re-enable RLS, rotate secrets after a compromise-driven restore; (4) define retry/alerting for failed backups; (5) ensure the simulation reset can never target a production project unintentionally.

**Status:** Documented
