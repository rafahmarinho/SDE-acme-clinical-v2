---
name: t2367-protect-data-at-rest-cloud-3-3
description: Protect ACME Clinical's files at rest in Supabase Storage (provider encryption, private buckets, version-by-key, lifecycle). Part 3/3 of a shared countermeasure tracked with T2292.
---

# T2367: Protect data at rest (Cloud) (3/3) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2367](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2367/)
**Priority:** 10/10 · **Phase:** deployment

**Guidance:** Encrypt sensitive volumes, managed database instances and object stores; enable versioning where possible; define a lifecycle/retention policy; restrict access to storage services.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.))
- Found: Files (e.g. report exports, observation attachments) stored in Supabase Storage.
- Missing: Object-store encryption and durability are Supabase-managed; Supabase Storage offers no object versioning toggle.
- Conclusion: Platform control, with bucket/RLS definitions expressible in `supabase/migrations/`.

**Recommended Action:**
Identical guidance to T2292 (1/3) and T2366 (2/3); track together using the T2292 checklist. Suggested evidence slice for this part: Storage.
- All buckets private; no bucket created with `public = true` for clinical files.
- RLS policies on `storage.objects` restrict reads/writes by role and ward/patient assignment.
- Signed URLs with short expiry (e.g. 60-300 seconds) for downloads.
- Versioning compensated by immutable keys (`reports/<id>/<timestamp>.pdf`) plus metadata rows; lifecycle job removes expired objects.
- File size and MIME type limits set per bucket.

**Status:** Documented
