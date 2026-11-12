---
name: t3990-schedule-regular-backups
description: AWS Backup is not used by ACME Clinical; apply the same backup practices (schedule, monitoring, lifecycle, encryption, deletion protection, recovery tests) to Supabase database backups/PITR and Storage.
---

# T3990: Schedule regular backups (NON-CODE)

**Category:** INFRA
**SD Elements:** [T3990](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T3990/)
**Priority:** 6/10 · **Phase:** deployment

**Guidance:** Use AWS Backup for AWS storage (S3, EBS, EFS): automated scheduled backups per a formal policy, monitoring and notifications for failures, lifecycle rules, Audit Manager compliance checks, encryption with restricted key access, deletion protection (Vault Lock) and regular recovery tests.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"), line 19 "publicados separadamente na Vercel" (EN: "published separately on Vercel"))
- Found: the stack is Supabase (PostgreSQL, Storage) and Vercel; no AWS account or AWS Backup resources are managed by the project (Supabase's underlying cloud is not customer-accessible).
- Missing: AWS resources to back up; backup scheduling is a Supabase plan feature.
- Conclusion: AWS Backup is not applicable. The practices map to Supabase: managed daily backups and PITR, retention by plan, restore to new project, and a separate copy of Storage objects if required.

**Recommended Action:** Platform owner: (1) write a backup policy (frequency, retention by data class) and select the Supabase plan/PITR that meets it; (2) monitor backup status in the Supabase Dashboard and add alerting for any off-site dump job; (3) if off-site copies are kept (e.g. object storage), enable encryption, restricted access, lifecycle rules and immutability/versioning; (4) restrict who can delete or restore projects (Supabase organization roles, MFA); (5) run regular restore tests into a non-production project.

**Status:** Documented
