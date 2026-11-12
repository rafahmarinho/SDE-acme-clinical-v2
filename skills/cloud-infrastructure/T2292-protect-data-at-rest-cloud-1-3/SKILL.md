---
name: t2292-protect-data-at-rest-cloud-1-3
description: Protect ACME Clinical's data at rest in hosted Supabase (PostgreSQL patient/observation data, Storage files, backups) through provider encryption, backups/PITR, retention policy and restricted access. Part 1/3 of a shared countermeasure.
---

# T2292: Protect data at rest (Cloud) (1/3) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2292](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2292/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Encrypt sensitive volumes, managed database instances and object stores; enable versioning where possible; define a lifecycle/retention policy; restrict access to storage services.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: Use current, stable technology versions and Supabase for PostgreSQL, email login and...) and line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.))
- Found: Patient, monitor, alarm, observation and report data are persisted in hosted Supabase PostgreSQL; files in Supabase Storage. Vercel functions are stateless (no attached volumes).
- Missing: Disk/volume and object-store encryption, backup schedules and PITR are provider-side. Supabase encrypts databases and Storage at rest (AES-256) by default; the customer cannot change the disk-level key.
- Conclusion: Platform control. Access restriction is partly code (RLS policies and private buckets in `supabase/migrations/`), covered by access-control CMs; this CM tracks the provider-side settings.

**Recommended Action:**
This is part 1/3. T2292, T2366 and T2367 have identical guidance; track together. This file is the master checklist.
- Encryption: confirm Supabase encryption at rest for Postgres and Storage (documented in Supabase's security/SOC 2 materials; record the evidence). For especially sensitive columns, use Supabase Vault for secrets; avoid storing secrets in plain tables.
- Volumes: none customer-managed (Vercel functions are ephemeral; do not write PHI to `/tmp`).
- Versioning/backup: Supabase daily backups are included on paid plans; enable the PITR add-on for production so the clinical record can be restored to any point (choose retention, e.g. 7-28 days). Supabase Storage has no object versioning; for report PDFs and attachments, use immutable object keys (new key per version) and store version metadata in Postgres.
- Lifecycle/retention: define retention per data class (demo patients, observations, alarm events, generated reports, logs); implement the deletion job in the API or a scheduled Supabase cron (`pg_cron`) via migration; document that the demo reset in the simulation area purges and reseeds demo data.
- Restrict access: Storage buckets private (`public = false`) with RLS on `storage.objects`; signed URLs with short expiry; service-role key only on the API; Supabase org members limited (see T2287).
- Repo config: bucket creation and RLS policies in `supabase/migrations/0001_schema.sql`; `pg_cron` retention jobs in a migration.

**Status:** Documented
