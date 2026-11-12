// Degraded-mode banner (T347/T433): shown when the API reports degraded mode (GET /v1/alarms/system-status)
// or any call fails with monitoring_unavailable / degraded_mode / busy. An empty screen must never look
// like "no alarms": the banner tells staff to check patients at the bedside.
import { useEffect, useState } from "react";
import { api, setDegradedHandler } from "../services/api";
import { useAuth } from "../auth/AuthContext";

const POLL_MS = 30_000;
const ERROR_HOLD_MS = 60_000;

export function DegradedBanner() {
  const { me } = useAuth();
  const canPoll = !!me?.permissions.includes("alarm:read");
  const [serverDegraded, setServerDegraded] = useState(false);
  const [errorUntil, setErrorUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setDegradedHandler(() => setErrorUntil(Date.now() + ERROR_HOLD_MS));
    return () => setDegradedHandler(null);
  }, []);

  useEffect(() => {
    if (!canPoll) return undefined;
    let active = true;
    const check = async () => {
      try {
        const status = await api.systemStatus();
        if (active) setServerDegraded(status.mode === "degraded");
      } catch {
        // an unreachable API is reported through the error handler (degraded codes) or the screens
      }
      if (active) setNow(Date.now());
    };
    void check();
    const timer = window.setInterval(() => void check(), POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [canPoll]);

  useEffect(() => {
    if (errorUntil <= Date.now()) return undefined;
    const timer = window.setTimeout(() => setNow(Date.now()), errorUntil - Date.now() + 10);
    setNow(Date.now());
    return () => window.clearTimeout(timer);
  }, [errorUntil]);

  if (!serverDegraded && errorUntil <= now) return null;
  return (
    <div className="alarm alarm-high" role="alert">
      <strong>Degraded mode.</strong> Live monitoring data may be delayed or unavailable. Check patients directly at the
      bedside.
    </div>
  );
}
