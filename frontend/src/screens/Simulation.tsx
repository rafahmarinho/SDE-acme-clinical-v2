import { useState, type FormEvent } from "react";
import { api } from "../services/api";
import { SCENARIOS, type Scenario } from "../services/types";
import { useAsync } from "../hooks/useAsync";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { formatDateTime, humanize } from "../lib/format";

const RESET_PHRASE = "RESET DEMO DATA";

const SCENARIO_HELP: Record<Scenario, string> = {
  normal: "All monitors report normal vital signs.",
  low_saturation: "Selected patients desaturate (SpO₂ falls below limits).",
  low_battery: "Selected monitors drain their battery and raise technical alarms.",
  sensor_fault: "Selected monitors report invalid or degraded signal quality.",
  connection_loss: "Selected monitors stop sending heartbeats.",
};

export default function Simulation() {
  const state = useAsync(() => api.simulation(), []);
  const monitors = useAsync(() => api.monitors(), []);
  const [scenario, setScenario] = useState<Scenario>("normal");
  const [monitorIds, setMonitorIds] = useState<string[]>([]);
  const [steps, setSteps] = useState(1);
  const [resetText, setResetText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    setResult(null);
    try {
      await fn();
    } catch (err) {
      setError(err);
      await state.reload();
    } finally {
      setBusy(null);
    }
  }

  const applyScenario = (e: FormEvent) => {
    e.preventDefault();
    void run("scenario", async () => {
      state.setData(await api.setScenario(scenario, monitorIds));
      setResult(`Scenario set to ${humanize(scenario)}.`);
    });
  };

  const advance = () =>
    run("advance", async () => {
      if (!state.data) return;
      const out = await api.advanceSimulation(steps, state.data.version);
      await state.reload();
      const parts = Object.entries(out)
        .filter(([, v]) => typeof v === "number" || typeof v === "string")
        .map(([k, v]) => `${humanize(k)}: ${String(v)}`);
      setResult(`Advanced ${steps} step(s). ${parts.join(" · ")}`);
    });

  const reset = (e: FormEvent) => {
    e.preventDefault();
    if (resetText !== RESET_PHRASE) return;
    void run("reset", async () => {
      state.setData(await api.resetSimulation(resetText));
      setResetText("");
      setResult("Demo data has been reset.");
    });
  };

  return (
    <section>
      <h1>Simulation</h1>
      <p className="muted">All patients, monitors and readings in ACME Clinical are fictitious demonstration data.</p>
      <ErrorMessage error={error ?? state.error} onRetry={state.reload} />
      {result && (
        <p role="status" className="notice">
          {result}
        </p>
      )}
      {state.loading && !state.data && <LoadingState />}
      {state.data && (
        <div className="stats">
          <div>
            <div className="big">{humanize(state.data.scenario)}</div>
            <div className="muted small">Current scenario</div>
          </div>
          <div>
            <div className="big">{state.data.tick}</div>
            <div className="muted small">Tick</div>
          </div>
          <div>
            <div className="big">v{state.data.version}</div>
            <div className="muted small">Updated {formatDateTime(state.data.updated_at)}</div>
          </div>
        </div>
      )}
      <div className="grid two">
        <form className="card" onSubmit={applyScenario} autoComplete="off">
          <h2>Scenario</h2>
          <label>
            Scenario
            <select value={scenario} onChange={(e) => setScenario(e.target.value as Scenario)}>
              {SCENARIOS.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </select>
          </label>
          <p className="muted small">{SCENARIO_HELP[scenario]}</p>
          <fieldset>
            <legend>Affected monitors (none selected = all; max 10)</legend>
            <ErrorMessage error={monitors.error} />
            <div className="grid three">
              {monitors.data?.map((m) => (
                <label key={m.id} className="checkbox">
                  <input
                    type="checkbox"
                    checked={monitorIds.includes(m.id)}
                    disabled={!monitorIds.includes(m.id) && monitorIds.length >= 10}
                    onChange={(e) => setMonitorIds(e.target.checked ? [...monitorIds, m.id] : monitorIds.filter((x) => x !== m.id))}
                  />
                  {m.serial}
                  {m.bed_label ? ` (${m.bed_label})` : ""}
                </label>
              ))}
            </div>
          </fieldset>
          <button type="submit" disabled={!!busy}>
            {busy === "scenario" ? "Applying…" : "Apply scenario"}
          </button>
        </form>
        <div className="card">
          <h2>Advance</h2>
          <label>
            Steps (1–60)
            <input type="number" min={1} max={60} value={steps} autoComplete="off" onChange={(e) => setSteps(Math.min(60, Math.max(1, Number(e.target.value) || 1)))} />
          </label>
          <button type="button" onClick={advance} disabled={!!busy || !state.data}>
            {busy === "advance" ? "Advancing…" : "Advance simulation"}
          </button>
          <form className="danger-zone" onSubmit={reset} autoComplete="off">
            <h2>Reset demo data</h2>
            <p>This deletes all readings, alarms and observations and restores the 12 demo patients and 10 monitors.</p>
            <label>
              Type <code>{RESET_PHRASE}</code> to confirm
              <input value={resetText} autoComplete="off" onChange={(e) => setResetText(e.target.value)} />
            </label>
            <button type="submit" className="danger" disabled={!!busy || resetText !== RESET_PHRASE}>
              {busy === "reset" ? "Resetting…" : "Reset demo data"}
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
