---
name: t4600-establish-out-of-band-communications-channel
description: Define out-of-band and fallback communication for ACME Clinical's critical flows (live monitoring and alarms over Supabase Realtime, Vercel API availability, incident communications), including degraded-mode behaviour when connectivity or data integrity is lost.
---

# T4600: Establish Out-of-Band Communications Channel (NON-CODE)

**Category:** INFRA
**SD Elements:** [T4600](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T4600/)
**Priority:** 10/10 · **Phase:** architecture-design

**Guidance:** Identify critical communication channels and data flows, set acceptable downtime and integrity thresholds, design physical and protocol redundancy, and implement fallbacks such as offline storage or batch processing.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 7 "senha, arquivos e atualizações em tempo real." (EN: password, files and real-time updates.) and line 37 "Simule leituras normais, saturação baixa, bateria fraca, problema no sensor e" (EN: Simulate normal readings, low saturation, low battery, sensor problem and) continued on line 39 "perda de conexão." (EN: loss of connection.))
- Found: Live monitoring and alarms depend on Supabase Realtime and the Vercel API. The PRD simulates monitor connection loss but defines no redundancy for the platform channels themselves.
- Missing: Physical/network redundancy (secondary links, alternative protocols) belongs to the hospital/organization network and to the providers' multi-AZ infrastructure, not to app code.
- Conclusion: Architecture/operations decision. Application-side fallbacks (Realtime reconnect, polling fallback, stale-data banner) are code and should be captured as a design requirement for `frontend/src/services` and `frontend/src/hooks`.

**Recommended Action:**
1. Critical flows (document in architecture notes): alarm generation (`backend/app/services/alarms.py`) to clinician screens via Realtime; alarm acknowledgement API; login/session; Supabase database availability.
2. Thresholds: define maximum tolerable staleness for live vitals/alarms (e.g. 10 s before showing a "connection lost - data stale" banner) and acceptable API downtime.
3. Redundancy:
   - Protocol redundancy: if the Realtime websocket drops, the frontend falls back to periodic HTTPS polling of the API; both paths must enforce the same auth.
   - Provider redundancy: understand Supabase region/HA options (read replicas, PITR) and Vercel multi-region functions (`regions` in `backend/vercel.json`); choose regions close to users.
   - Out-of-band human channel: because this is a clinical alarm system, the organization must keep a non-software escalation path (bedside monitor local alarms, phone/pager to nursing station) and state clearly in the README that ACME Clinical is a demo not a certified alarm system.
   - Incident communications: an out-of-band channel (phone bridge/SMS group, status page) for ops when Vercel/Supabase or corporate chat are down.
4. Fallbacks: frontend shows last-known values with timestamps and never silently hides alarms; queued acknowledgements are retried, not dropped; batch reconciliation of events after reconnection.

**Status:** Documented
