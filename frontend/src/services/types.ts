// Response/request shapes mirroring backend/app/schemas/__init__.py (UUIDs and datetimes arrive as strings).

export type Role = "nurse" | "physician" | "biomed_tech" | "admin";

export type Permission =
  | "patient:read"
  | "observation:write"
  | "alarm:read"
  | "alarm:ack"
  | "threshold:write"
  | "device:read"
  | "device:write"
  | "maintenance:write"
  | "report:read"
  | "file:write"
  | "break_glass:request"
  | "break_glass:review"
  | "staff:manage"
  | "settings:manage"
  | "simulation:control"
  | "events:read_all";

export interface Me {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  ward_ids: string[];
  permissions: Permission[];
  previous_login_at: string | null;
  privacy_notice_accepted_at: string | null;
  session_idle_minutes: number;
}

export interface SessionStart {
  previous_login_at: string | null;
  previous_login_ip: string | null;
}

export interface ProfileExport {
  profile: Record<string, unknown>;
  ward_ids: string[];
  observations_authored: number;
  events: Record<string, unknown>[];
  exported_at: string;
}

export interface Page<T> {
  items: T[];
  next_offset: number | null;
}

export interface Ward {
  id: string;
  code: string;
  name: string;
  bed_count: number;
  patient_count: number;
  active_alarms: number;
}

export interface Patient {
  id: string;
  pseudonym: string;
  display_name: string;
  birth_year: number | null;
  ward_id: string;
  bed_label: string | null;
  monitor_serial: string | null;
  active_alarms: number;
  admitted_at: string;
}

export type ReadingQuality = "good" | "degraded" | "invalid";

export interface Reading {
  recorded_at: string;
  heart_rate: number | null;
  spo2: number | null;
  resp_rate: number | null;
  bp_systolic: number | null;
  bp_diastolic: number | null;
  ecg: number[] | null;
  quality: ReadingQuality | string;
}

export interface Observation {
  id: string;
  author_name: string;
  body: string;
  created_at: string;
}

export type AlarmPriority = "high" | "medium" | "low";
export type AlarmState = "active" | "resolved";

export interface Alarm {
  id: string;
  patient_id: string | null;
  patient_pseudonym: string | null;
  monitor_serial: string;
  type: string;
  priority: AlarmPriority | string;
  state: AlarmState | string;
  message: string;
  raised_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by_name: string | null;
}

export type VitalParameter = "heart_rate" | "spo2" | "resp_rate" | "bp_systolic" | "bp_diastolic";

export const VITAL_PARAMETERS: readonly VitalParameter[] = ["heart_rate", "spo2", "resp_rate", "bp_systolic", "bp_diastolic"];

/** Mirrors THRESHOLD_BOUNDS on the server (the server re-validates). */
export const THRESHOLD_BOUNDS: Record<VitalParameter, [number, number]> = {
  heart_rate: [20, 250],
  spo2: [70, 100],
  resp_rate: [4, 60],
  bp_systolic: [50, 250],
  bp_diastolic: [30, 150],
};

export const VITAL_LABELS: Record<VitalParameter, { label: string; unit: string }> = {
  heart_rate: { label: "Heart rate", unit: "bpm" },
  spo2: { label: "SpO₂", unit: "%" },
  resp_rate: { label: "Respiration", unit: "/min" },
  bp_systolic: { label: "BP systolic", unit: "mmHg" },
  bp_diastolic: { label: "BP diastolic", unit: "mmHg" },
};

export interface Threshold {
  id: string;
  ward_id: string | null;
  patient_id: string | null;
  parameter: VitalParameter;
  low_limit: number;
  high_limit: number;
  updated_at: string;
}

export interface ThresholdUpdate {
  parameter: VitalParameter;
  low_limit: number;
  high_limit: number;
  confirm: true;
}

export type MonitorStatus = "online" | "offline" | "maintenance" | "retired";

export interface Monitor {
  id: string;
  serial: string;
  model: string;
  firmware_version: string;
  status: MonitorStatus | string;
  battery_pct: number;
  last_heartbeat_at: string | null;
  bed_id: string | null;
  bed_label: string | null;
  ward_id: string | null;
}

export type MaintenanceKind = "inspection" | "calibration" | "battery_replacement" | "repair" | "firmware_update";
export const MAINTENANCE_KINDS: readonly MaintenanceKind[] = [
  "inspection",
  "calibration",
  "battery_replacement",
  "repair",
  "firmware_update",
];

export interface MaintenanceRecord {
  id: string;
  monitor_id: string;
  kind: MaintenanceKind | string;
  notes: string;
  performed_by_name: string;
  performed_at: string;
  next_due: string | null;
}

export interface MaintenanceIn {
  kind: MaintenanceKind;
  notes: string;
  next_due: string | null;
}

export interface Staff {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  ward_ids: string[];
  last_login_at: string | null;
}

export interface StaffInvite {
  email: string;
  full_name: string;
  role: Role;
  ward_ids: string[];
}

export interface StaffUpdate {
  role?: Role;
  is_active?: boolean;
  ward_ids?: string[];
}

export interface SecuritySettings {
  password_min_length: number;
  session_idle_minutes: number;
  session_absolute_hours: number;
  max_concurrent_sessions: number;
  lockout_threshold: number;
  lockout_minutes: number;
  require_mfa_for_admin: boolean;
  data_retention_days: number;
  updated_at: string;
}

export type SecuritySettingsUpdate = Partial<Omit<SecuritySettings, "updated_at">>;

export type Scenario = "normal" | "low_saturation" | "low_battery" | "sensor_fault" | "connection_loss";
export const SCENARIOS: readonly Scenario[] = ["normal", "low_saturation", "low_battery", "sensor_fault", "connection_loss"];

export interface SimulationState {
  scenario: Scenario;
  tick: number;
  version: number;
  updated_at: string;
}

export interface EventRecord {
  id: number;
  occurred_at: string;
  actor_role: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  outcome: string;
  details: Record<string, unknown>;
}

export interface IntegrityResult {
  intact: boolean;
  first_broken_id: number | null;
}

export interface Attachment {
  id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface SignedUrl {
  url: string;
  expires_in: number;
}

export interface WardReport {
  ward_id: string | null;
  period_start: string;
  period_end: string;
  alarm_counts: Record<string, number>;
  mean_time_to_ack_seconds: number | null;
  unacknowledged_high_priority: number;
  readings_count: number;
  generated_at: string;
}

export interface BreakGlassGrant {
  id: string;
  patient_id: string;
  expires_at: string;
}
