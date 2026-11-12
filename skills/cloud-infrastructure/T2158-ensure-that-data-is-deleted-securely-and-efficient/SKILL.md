---
name: t2158-ensure-that-data-is-deleted-securely-and-efficient
description: Media-level secure erasure of ACME Clinical data is performed by Supabase (and Vercel for logs/build artifacts); as cloud customer, ACME must request, confirm and follow up deletions (projects, backups, Storage objects, log drains) and handle mistaken or unauthorized deletions.
---

# T2158: Ensure that data is deleted securely and efficiently from storage (Cloud) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2158](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/activities/32-T2158/)
**Priority:** 7/10 · **Phase:** activities

**Guidance:** Providers must erase objects (including redundant copies) on request, block new access at deletion time, handle race conditions, provide signed time-stamped confirmation, and support undo of incorrect or unauthorized deletions. Customers must notify the provider of incorrect/unauthorized deletions, confirm erasure, and follow up on incomplete deletion (NIST, Erase Data Objects in a Cloud).

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 43 "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados" (EN: choose scenarios, advance the simulation, view events and reset the data. The results) and line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.))
- Found: Data and files live in Supabase Postgres and Storage; logs in Vercel/Supabase and any drain destination. The PRD's "reset data" is an application-level purge and reseed of demo data.
- Missing: Media sanitization, erasure of redundant copies and backups, and signed deletion confirmations are provider processes governed by the Supabase/Vercel DPA, not code.
- Conclusion: Provider (as cloud provider) and organization (as cloud customer) process. The in-app reset/delete paths are code and are covered by data-management CMs; they delete logically but backups/PITR retain data until expiry.

**Recommended Action:**
As cloud customer (ACME ops/privacy):
- Review the Supabase and Vercel DPAs for deletion timelines, backup expiry and media sanitization commitments; file them as evidence.
- Document that deleted rows/objects persist in Supabase daily backups and PITR WAL until the retention window ends (e.g. 7-28 days); state this in the privacy notice/retention policy.
- Project decommissioning: deleting a Supabase project removes the database, Storage and backups; download any required records first and record the deletion date. Also remove stale preview/branch projects and Vercel deployments containing data.
- Storage deletion: delete via the Storage API (not by removing metadata rows directly) so objects are removed from the underlying store; verify with a follow-up list/GET.
- Logs: configure retention/expiry on the log drain destination; ensure no patient data is in logs so log deletion is less critical.
- Mistaken or unauthorized deletion: use PITR to restore; for unauthorized deletions via a compromised console account, contact Supabase/Vercel support immediately and follow the incident plan.
- Follow-up: if a requested deletion (e.g. account closure) is not confirmed by the provider within the agreed time, open a support ticket and record the response.

**Status:** Documented
