---
name: t433-design-a-fallback-mechanism-or-a-degraded-mode-for
description: Design an ACME Clinical degraded mode that keeps live vitals, alarms and alarm acknowledgement working when Supabase Realtime, the 3D view, reports or parts of the backend fail or are overloaded, with polling fallback and load shedding of non-essential features.
---

# T433: Design a fallback mechanism or a degraded mode for the system

**Category:** CODE_FIX
**SD Elements:** [T433](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T433/)
**Priority:** 8/10 · **Phase:** architecture-design

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: "...password, files and real-time updates. I want the screens working and the data")
> Source: specs/PRD.md, line 7

> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: "limit settings, reports and staff management (you can create something very visual in 3D if")
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
The live monitoring screen would depend entirely on Supabase Realtime and a heavy 3D scene. If the websocket drops or the browser struggles, the screen freezes or blanks with no indication, and alarms stop appearing even though the backend still generates them.

**Secure Implementation Pattern:**
```ts
// frontend/src/hooks/useLiveVitals.ts
export function useLiveVitals(wardId: string) {
  const [mode, setMode] = useState<"realtime" | "polling" | "offline">("realtime");
  const lastMsg = useRef(Date.now());
  const realtimeOk = useRef(true);

  useEffect(() => {
    const ch = supabase.channel(`ward:${wardId}`)
      .on("postgres_changes", { event: "INSERT", schema: "clinical", table: "alarms",
           filter: `ward_id=eq.${wardId}` }, (p) => { lastMsg.current = Date.now(); onAlarm(p.new); })
      .subscribe((s) => { realtimeOk.current = s === "SUBSCRIBED"; if (!realtimeOk.current) setMode("polling"); });
    const t = setInterval(async () => {
      if (Date.now() - lastMsg.current > 10_000 || !realtimeOk.current) {
        try { applySnapshot(await api.get(`/wards/${wardId}/live`)); setMode((m) => m === "offline" ? "polling" : m); }
        catch { setMode("offline"); }                     // banner: "Live data unavailable"
      }
    }, 3_000);
    return () => { clearInterval(t); supabase.removeChannel(ch); };
  }, [wardId]);
  return mode;
}
```
```python
# backend/app/core/degraded.py -- feature flags flipped by health checks or overload
ESSENTIAL = {"live_vitals", "alarms", "alarm_ack", "break_glass"}
def degraded_guard(feature: str):
    async def dep():
        if state.degraded and feature not in ESSENTIAL:
            raise HTTPException(503, "Temporarily unavailable (degraded mode)", headers={"Retry-After": "30"})
    return Depends(dep)
```

**Implementation Guidance:**
- Essential/emergency functions in degraded mode: live vitals snapshot, alarm list, alarm acknowledgement, observations, break-glass. Deferred: reports generation, 3D visualization, staff management, simulation scenario editing.
- Frontend fallback: Realtime → REST polling → offline banner with last update time; the 3D view is lazy-loaded with a 2D tile grid fallback (`frontend/src/components/WardGrid.tsx`) if WebGL is unavailable or frame rate drops.
- Backend: `backend/app/core/degraded.py` toggles `state.degraded` when DB latency/error rate exceeds thresholds; non-essential routers depend on `degraded_guard`.
- Alarm generation stays in Python (`services/alarms.py`) and does not depend on Realtime; Realtime is only the delivery channel.
- Show a persistent "Degraded mode" banner so users know some data may be delayed.
- Reference: SD Elements guidance for T433.

**Success Criteria:**
- [ ] With Realtime disabled, live vitals and new alarms still appear within 5 s via polling.
- [ ] In degraded mode, reports/3D/staff endpoints return 503 while alarms and acknowledgement keep working.
- [ ] Degraded/offline state is visibly indicated in the UI.

**Status:** Pending
