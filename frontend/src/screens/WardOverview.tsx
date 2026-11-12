import { Link } from "react-router-dom";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../auth/AuthContext";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";

export default function WardOverview() {
  const { can } = useAuth();
  const { data, error, loading, reload } = useAsync(() => api.wards(), []);

  return (
    <section>
      <div className="page-head">
        <h1>Ward overview</h1>
        <button type="button" className="secondary" onClick={reload}>
          Refresh
        </button>
      </div>
      {loading && !data && <LoadingState />}
      <ErrorMessage error={error} onRetry={reload} />
      {data && data.length === 0 && <p className="muted">No wards are assigned to you.</p>}
      <div className="grid cards">
        {data?.map((w) => (
          <article key={w.id} className={`card ward ${w.active_alarms > 0 ? "ward-alarming" : ""}`}>
            <div className="muted small">{w.code}</div>
            <h2>{w.name}</h2>
            <div className="stats">
              <div>
                <div className="big">{w.patient_count}</div>
                <div className="muted small">Patients</div>
              </div>
              <div>
                <div className="big">{w.bed_count}</div>
                <div className="muted small">Beds</div>
              </div>
              <div>
                <div className={`big ${w.active_alarms > 0 ? "danger" : ""}`}>{w.active_alarms}</div>
                <div className="muted small">Active alarms</div>
              </div>
            </div>
            <div className="row">
              {can("patient:read") && <Link to={`/patients?ward_id=${encodeURIComponent(w.id)}`}>Patients</Link>}
              <Link to={`/alarms?ward_id=${encodeURIComponent(w.id)}`}>Alarms</Link>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
