import { useEffect, useState } from "react";
import { api } from "../services/api";
import { useAuth } from "../auth/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { ThresholdEditor } from "../components/ThresholdEditor";

export default function Thresholds() {
  const { can } = useAuth();
  const wards = useAsync(() => api.wards(), []);
  const [wardId, setWardId] = useState("");
  useEffect(() => {
    if (!wardId && wards.data?.[0]) setWardId(wards.data[0].id);
  }, [wards.data, wardId]);
  const thresholds = useAsync(() => api.thresholds({ ward_id: wardId }), [wardId], !!wardId);
  const ward = wards.data?.find((w) => w.id === wardId);

  return (
    <section>
      <h1>Alarm limits</h1>
      <p className="muted">
        Ward default limits apply to every patient in the ward unless a patient-specific override is set on the patient page.
        {!can("threshold:write") && " You can view limits; changing them requires a physician assigned to the ward."}
      </p>
      <ErrorMessage error={wards.error} onRetry={wards.reload} />
      {wards.loading && !wards.data && <LoadingState />}
      {wards.data && (
        <label className="inline">
          Ward
          <select value={wardId} onChange={(e) => setWardId(e.target.value)}>
            {wards.data.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <ErrorMessage error={thresholds.error} onRetry={thresholds.reload} />
      {thresholds.loading && !thresholds.data && wardId && <LoadingState />}
      {thresholds.data && ward && (
        <div className="card">
          <ThresholdEditor
            thresholds={thresholds.data.filter((t) => t.patient_id === null)}
            editable={can("threshold:write")}
            scopeLabel={`Ward ${ward.name}`}
            onSave={async (body) => {
              await api.setWardThreshold(ward.id, body);
              await thresholds.reload();
            }}
          />
        </div>
      )}
    </section>
  );
}
