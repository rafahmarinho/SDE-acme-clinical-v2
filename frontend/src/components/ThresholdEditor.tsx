// Alarm-limit editor shared by the Thresholds screen (ward scope) and PatientDetail (patient scope).
// Every change requires an explicit confirmation checkbox, sent to the API as `confirm: true`.
import { useState, type FormEvent } from "react";
import { THRESHOLD_BOUNDS, VITAL_LABELS, VITAL_PARAMETERS, type Threshold, type ThresholdUpdate, type VitalParameter } from "../services/types";
import { ErrorMessage } from "./ErrorMessage";
import { formatDateTime } from "../lib/format";

interface Props {
  thresholds: Threshold[];
  /** Ward defaults shown for comparison when editing patient overrides. */
  inherited?: Threshold[];
  editable: boolean;
  scopeLabel: string;
  onSave: (body: ThresholdUpdate) => Promise<void>;
}

export function ThresholdEditor({ thresholds, inherited = [], editable, scopeLabel, onSave }: Props) {
  const [editing, setEditing] = useState<VitalParameter | null>(null);
  const [low, setLow] = useState(0);
  const [high, setHigh] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const byParam = new Map(thresholds.map((t) => [t.parameter, t]));
  const inheritedByParam = new Map(inherited.map((t) => [t.parameter, t]));

  function startEdit(p: VitalParameter) {
    const current = byParam.get(p) ?? inheritedByParam.get(p);
    const [lo, hi] = THRESHOLD_BOUNDS[p];
    setLow(current?.low_limit ?? lo);
    setHigh(current?.high_limit ?? hi);
    setConfirmed(false);
    setError(null);
    setEditing(p);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!editing) return;
    const [lo, hi] = THRESHOLD_BOUNDS[editing];
    if (!(lo <= low && low < high && high <= hi)) {
      setError(`Limits must satisfy ${lo} ≤ low < high ≤ ${hi}.`);
      return;
    }
    if (!confirmed) {
      setError("Tick the confirmation box to change a clinical alarm limit.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave({ parameter: editing, low_limit: low, high_limit: high, confirm: true });
      setEditing(null);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <table className="table">
        <thead>
          <tr>
            <th>Parameter</th>
            <th>Low</th>
            <th>High</th>
            <th>Source</th>
            <th>Updated</th>
            {editable && <th />}
          </tr>
        </thead>
        <tbody>
          {VITAL_PARAMETERS.map((p) => {
            const own = byParam.get(p);
            const shown = own ?? inheritedByParam.get(p);
            return (
              <tr key={p}>
                <td>
                  {VITAL_LABELS[p].label} ({VITAL_LABELS[p].unit})
                </td>
                <td className="strong">{shown?.low_limit ?? "—"}</td>
                <td className="strong">{shown?.high_limit ?? "—"}</td>
                <td>{own ? scopeLabel : shown ? "Ward default" : "Not set"}</td>
                <td>{formatDateTime(shown?.updated_at)}</td>
                {editable && (
                  <td>
                    <button type="button" className="secondary" onClick={() => startEdit(p)}>
                      Change
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {editing && (
        <form className="card confirm-box" onSubmit={submit} autoComplete="off">
          <h3>
            Change {VITAL_LABELS[editing].label} limits — {scopeLabel}
          </h3>
          <ErrorMessage error={error} />
          <div className="row">
            <label>
              Low limit
              <input type="number" value={low} autoComplete="off" min={THRESHOLD_BOUNDS[editing][0]} max={THRESHOLD_BOUNDS[editing][1]} onChange={(e) => setLow(Number(e.target.value))} />
            </label>
            <label>
              High limit
              <input type="number" value={high} autoComplete="off" min={THRESHOLD_BOUNDS[editing][0]} max={THRESHOLD_BOUNDS[editing][1]} onChange={(e) => setHigh(Number(e.target.value))} />
            </label>
          </div>
          <p className="muted small">
            Allowed range {THRESHOLD_BOUNDS[editing][0]}–{THRESHOLD_BOUNDS[editing][1]} {VITAL_LABELS[editing].unit}.
          </p>
          <label className="checkbox">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I confirm this
            change to a clinical alarm limit. It takes effect immediately and is recorded in the audit log.
          </label>
          <div className="row">
            <button type="submit" disabled={busy || !confirmed}>
              {busy ? "Saving…" : "Save limits"}
            </button>
            <button type="button" className="secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
