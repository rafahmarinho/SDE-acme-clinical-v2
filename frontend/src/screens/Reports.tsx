import { useState } from "react";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../auth/AuthContext";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { formatDateTime, humanize } from "../lib/format";

const PERIODS = [
  { hours: 8, label: "Last 8 hours (shift)" },
  { hours: 24, label: "Last 24 hours" },
  { hours: 24 * 7, label: "Last 7 days" },
  { hours: 24 * 30, label: "Last 30 days" },
];

/** Small counts are suppressed by the API (null) so individuals cannot be singled out (P7). */
export function formatCount(count: number | null): string {
  return count === null ? "fewer than 5" : String(count);
}

export default function Reports() {
  const wards = useAsync(() => api.wards(), []);
  const [wardId, setWardId] = useState("");
  const [hours, setHours] = useState(24);
  const report = useAsync(() => api.wardActivity({ ward_id: wardId || undefined, hours }), [wardId, hours]);
  const r = report.data;
  const { can } = useAuth();
  const [exportError, setExportError] = useState<unknown>(null);
  const exportCsv = async (kind: "ward_activity" | "audit_events") => {
    setExportError(null);
    try {
      await api.exportCsv(kind, { ward_id: wardId || undefined, hours });
    } catch (err) {
      setExportError(err);
    }
  };
  const totalAlarms = r ? Object.values(r.alarm_counts).reduce<number>((a, b) => a + (b ?? 0), 0) : 0;

  return (
    <section>
      <h1>Ward activity report</h1>
      <div className="filter-bar">
        <label className="inline">
          Ward
          <select value={wardId} onChange={(e) => setWardId(e.target.value)}>
            <option value="">All my wards</option>
            {wards.data?.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        <label className="inline">
          Period
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            {PERIODS.map((p) => (
              <option key={p.hours} value={p.hours}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary" onClick={report.reload}>
          Regenerate
        </button>
        <button type="button" className="secondary" onClick={() => void exportCsv("ward_activity")}>
          Export CSV
        </button>
        {can("events:read_all") && (
          <button type="button" className="secondary" onClick={() => void exportCsv("audit_events")}>
            Export audit events (CSV)
          </button>
        )}
      </div>
      <ErrorMessage error={exportError} />
      <ErrorMessage error={report.error} onRetry={report.reload} />
      {report.loading && <LoadingState label="Generating report…" />}
      {r && (
        <>
          <p className="muted">
            {formatDateTime(r.period_start)} – {formatDateTime(r.period_end)} · generated {formatDateTime(r.generated_at)}
          </p>
          <div className="stats">
            <div>
              <div className="big">{totalAlarms}</div>
              <div className="muted small">Alarms raised</div>
            </div>
            <div>
              <div className="big">{r.mean_time_to_ack_seconds == null ? "—" : `${Math.round(r.mean_time_to_ack_seconds)} s`}</div>
              <div className="muted small">Mean time to acknowledge</div>
            </div>
            <div>
              <div className={`big ${r.unacknowledged_high_priority > 0 ? "danger" : ""}`}>{r.unacknowledged_high_priority}</div>
              <div className="muted small">Unacknowledged high priority</div>
            </div>
            <div>
              <div className="big">{r.readings_count}</div>
              <div className="muted small">Readings</div>
            </div>
          </div>
          <div className="card">
            <h2>Alarms by type</h2>
            {Object.keys(r.alarm_counts).length === 0 ? (
              <p className="muted">No alarms in this period.</p>
            ) : (
              <table className="table">
                <tbody>
                  {Object.entries(r.alarm_counts).map(([type, count]) => (
                    <tr key={type}>
                      <td>{humanize(type)}</td>
                      <td className="strong">{formatCount(count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </section>
  );
}
