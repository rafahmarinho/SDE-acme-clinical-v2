---
name: t342-inform-and-warn-users-about-using-critical-system
description: Show explicit, acknowledged warnings before ACME Clinical critical actions (changing alarm limits, acknowledging alarms whose condition continues, resetting demo data, staff role changes, unbinding monitors, break-glass) and a system-use notice at login stating activity is audited.
---

# T342: Inform and warn users about using critical system services

**Category:** CODE_FIX
**SD Elements:** [T342](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/development/32-T342/)
**Priority:** 5/10 · **Phase:** development

**Spec Context:**
> "acompanhar manutenção. Reconhecer um alarme não encerra uma condição que ainda está"
> "acontecendo. Simule leituras normais, saturação baixa, bateria fraca, problema no sensor e"
> (EN: "...track maintenance. Acknowledging an alarm does not end a condition that is still happening. Simulate normal readings, low saturation, low battery, sensor problem and")
> Source: specs/PRD.md, lines 35-37

> "escolher cenários, avançar a simulação, consultar eventos e reiniciar os dados. Os resultados"
> (EN: "choose scenarios, advance the simulation, view events and reset the data. The results")
> Source: specs/PRD.md, line 43

**What the spec implies (naive approach):**
"Acknowledge", "Save limits" and "Reset data" would be plain buttons. Users might believe acknowledging resolves the alarm, widen limits without realizing the clinical impact, or wipe all demo data with a misclick, with no notice that these actions are audited.

**Secure Implementation Pattern:**
```tsx
// frontend/src/components/CriticalActionDialog.tsx
type Props = { title: string; consequences: string[]; confirmWord?: string;
               onConfirm: (ack: { acknowledged: true; reason?: string }) => Promise<void> };

export function CriticalActionDialog({ title, consequences, confirmWord, onConfirm }: Props) {
  const [checked, setChecked] = useState(false);
  const [typed, setTyped] = useState("");
  const ready = checked && (!confirmWord || typed === confirmWord);
  return (
    <Dialog role="alertdialog" aria-labelledby="crit-title">
      <h2 id="crit-title">{title}</h2>
      <ul>{consequences.map((c) => <li key={c}>{c}</li>)}</ul>
      <p>This action is recorded in the audit log with your name and time.
         You are responsible for actions taken with your account.</p>
      <label><input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
        I understand and want to continue</label>
      {confirmWord && <input aria-label={`Type ${confirmWord} to confirm`} value={typed}
                             onChange={(e) => setTyped(e.target.value)} />}
      <button disabled={!ready} onClick={() => onConfirm({ acknowledged: true })}>Confirm</button>
    </Dialog>
  );
}

// usage on alarm acknowledgement
<CriticalActionDialog title="Acknowledge alarm"
  consequences={["Acknowledging silences the alert temporarily; it does NOT resolve the condition.",
                 "If SpO2 remains below the limit the alarm stays active and re-alerts in 2 minutes."]}
  onConfirm={(a) => api.post(`/alarms/${id}/ack`, a)} />
```

**Implementation Guidance:**
- Critical features: alarm threshold changes (show old vs new values and affected patients), alarm acknowledgement while condition is active, simulation reset (type `RESET`), staff role/deactivation changes, unbinding a monitor from an occupied bed, break-glass (T337).
- Login screen (`frontend/src/screens/LoginScreen.tsx`) shows a system-use notice: demo system with fictional data, authorized staff only, activity is monitored and audited; users must accept once per session before entering. The "government information system" clause is not applicable.
- Backend enforces acknowledgement: Pydantic models for these endpoints require `acknowledged: Literal[True]` (and `confirm: Literal["RESET"]` for reset), so the warning cannot be skipped via the API.
- Response messages for critical actions repeat the outcome ("Alarm acknowledged — condition still active").
- All text in English, per the PRD.
- Reference: SD Elements guidance for T342.

**Success Criteria:**
- [ ] Each listed critical action opens `CriticalActionDialog`; confirm disabled until explicit acknowledgement.
- [ ] API rejects those requests (422) without the acknowledgement fields.
- [ ] Login shows the system-use notice and requires acceptance.

**Status:** Applied
