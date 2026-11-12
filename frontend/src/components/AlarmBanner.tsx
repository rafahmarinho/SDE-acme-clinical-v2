import type { ReactNode } from "react";
import type { Alarm } from "../services/types";
import { formatDateTime, humanize } from "../lib/format";

export function alarmStatusLabel(a: Pick<Alarm, "state" | "acknowledged_at">): string {
  if (a.state === "resolved") return "Resolved";
  return a.acknowledged_at ? "STILL ACTIVE — acknowledged, condition ongoing" : "ACTIVE — not acknowledged";
}

/** Single alarm card. Acknowledged alarms that are still active keep the active styling and label. */
export function AlarmBanner({ alarm, children }: { alarm: Alarm; children?: ReactNode }) {
  const active = alarm.state === "active";
  const cls = [
    "alarm",
    `alarm-${alarm.priority}`,
    active ? "alarm-active" : "alarm-resolved",
    active && alarm.acknowledged_at ? "alarm-acked" : "",
  ].join(" ");
  return (
    <div className={cls} role={active && !alarm.acknowledged_at && alarm.priority === "high" ? "alert" : undefined}>
      <div className="alarm-head">
        <span className="badge">{String(alarm.priority).toUpperCase()}</span>
        <span className="alarm-status">{alarmStatusLabel(alarm)}</span>
        <span className="muted small">{humanize(alarm.type)}</span>
      </div>
      <div className="alarm-message">{alarm.message}</div>
      <div className="muted small">
        {alarm.patient_pseudonym ? `Patient ${alarm.patient_pseudonym} · ` : ""}Monitor {alarm.monitor_serial} · Raised{" "}
        {formatDateTime(alarm.raised_at)} · Last seen {formatDateTime(alarm.last_seen_at)}
        {alarm.acknowledged_at &&
          ` · Acknowledged ${formatDateTime(alarm.acknowledged_at)}${alarm.acknowledged_by_name ? ` by ${alarm.acknowledged_by_name}` : ""}`}
        {alarm.resolved_at && ` · Resolved ${formatDateTime(alarm.resolved_at)}`}
      </div>
      {children}
    </div>
  );
}
