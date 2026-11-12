---
name: t434-verify-that-the-system-has-a-fallback-mechanism-or
description: Test that ACME Clinical keeps live vitals, alarms and acknowledgement available under simulated overload, Realtime outage and component failure, while non-essential features are shed and the degraded state is shown.
---

# T434: Verify that the system has a fallback mechanism or a degraded mode

**Category:** CODE_FIX
**SD Elements:** [T434](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T434/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: "...password, files and real-time updates. I want the screens working and the data")
> Source: specs/PRD.md, line 7

**What the spec implies (naive approach):**
The fallback design from T433 is easy to break silently (e.g. a new endpoint not tagged essential, polling disabled). Without tests that simulate failures and load, the first real outage is the test.

**Secure Implementation Pattern:**
```python
# backend/tests/test_degraded_mode.py
async def test_essential_functions_survive_degraded_mode(client_as, set_degraded, alarm):
    set_degraded(True)
    nurse = client_as("nurse")
    assert (await nurse.get("/api/wards/{w}/live".format(w=alarm.ward_id))).status_code == 200
    assert (await nurse.post(f"/api/alarms/{alarm.id}/ack", json={"note": "seen"})).status_code == 200
    assert (await client_as("administrator").post("/api/reports", json={})).status_code == 503

async def test_overload_sheds_low_priority(load, client_as):
    # 200 concurrent report requests must not starve alarm reads
    async with load(concurrency=200, path="/api/reports", role="physician"):
        r = await client_as("nurse").get("/api/alarms?active=true")
    assert r.status_code == 200 and r.elapsed.total_seconds() < 1.0
```
```ts
// frontend/src/hooks/useLiveVitals.test.ts (vitest, fake timers)
it("falls back to polling when realtime fails", async () => {
  mockRealtimeStatus("CHANNEL_ERROR");
  const { result } = renderHook(() => useLiveVitals("ward-a"));
  await vi.advanceTimersByTimeAsync(3_500);
  expect(api.get).toHaveBeenCalledWith("/wards/ward-a/live");
  expect(result.current).toBe("polling");
});
```

**Implementation Guidance:**
- Simulate: Realtime outage (block websocket), DB slowness (inject latency in `backend/app/db.py` test double), excessive requests (locust or `httpx` concurrency against a Vercel preview), WebGL unavailable (3D view fallback).
- Assert essential functions (live vitals, alarms, acknowledgement, break-glass) remain usable and within latency budget; non-essential return 503 with `Retry-After`.
- Check the UI banner and last-updated timestamp in degraded/offline modes (Playwright).
- Record a manual load test result for the deployed API in the test log.
- Reference: SD Elements guidance for T434.

**Success Criteria:**
- [ ] Degraded-mode backend tests and frontend fallback tests pass in CI.
- [ ] Load test shows alarm endpoints stay responsive while reports are shed.
- [ ] Banner visible during outages (E2E screenshot assertion).

**Status:** Pending
