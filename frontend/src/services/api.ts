// Typed client for the ACME Clinical API (FastAPI).
// * Attaches the Supabase access token as a Bearer token; no cookies (credentials: "omit").
// * Sends JSON bodies; query strings carry only ids/filters (guarded below). Searches use POST bodies.
// * Generates an X-Request-Id per call and maps errors to the API's {error, code, fields?, request_id} shape.
// * 401 => local sign-out and redirect to /login, EXCEPT a step-up challenge (code "step_up_required"):
//   the registered step-up handler asks the user to re-authenticate and the request is retried once.
// * Degraded-mode codes (monitoring_unavailable / degraded_mode / busy) notify the degraded-mode banner.
import { getAccessToken, supabase } from "../lib/supabase";
import type {
  ActiveGrant,
  AdvanceResult,
  Alarm,
  AlarmAckResult,
  Attachment,
  Bed,
  BreakGlassGrant,
  BreakGlassOutcome,
  ErasureRequest,
  EventRecord,
  IntegrityResult,
  InviteAccepted,
  MaintenanceIn,
  MaintenanceRecord,
  Me,
  Monitor,
  MonitorState,
  Observation,
  Page,
  Patient,
  PendingGrant,
  Reading,
  ReportKind,
  Role,
  RoleRequest,
  Scenario,
  SecuritySettings,
  SecuritySettingsUpdate,
  SessionStart,
  SignedUrl,
  SimulationActionResult,
  SimulationState,
  Staff,
  StaffInvite,
  StaffUpdate,
  SystemStatus,
  Threshold,
  ThresholdUpdate,
  Ward,
  WardReport,
} from "./types";

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly fields: FieldError[];
  readonly requestId: string | null;
  /** Machine-readable code from the API error catalogue (e.g. "step_up_required", "degraded_mode"). */
  readonly code: string | null;
  readonly degraded: boolean;

  constructor(
    status: number,
    message: string,
    fields: FieldError[] = [],
    requestId: string | null = null,
    code: string | null = null,
    degraded = false,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
    this.requestId = requestId;
    this.code = code;
    this.degraded = degraded;
  }
}

/** Error codes meaning the platform is degraded (T347/T433): the UI shows the degraded-mode banner. */
export const DEGRADED_CODES: ReadonlySet<string> = new Set(["monitoring_unavailable", "degraded_mode", "busy"]);

export function isDegradedError(err: unknown): boolean {
  return err instanceof ApiError && (err.degraded || (err.code !== null && DEGRADED_CODES.has(err.code)));
}

export type QueryValue = string | number | boolean | null | undefined;
export type Query = Record<string, QueryValue>;

interface RequestOptions {
  query?: Query;
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Internal: set on the single retry after a successful step-up re-authentication. */
  stepUpRetried?: boolean;
}

function apiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL;
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new Error("Missing required environment variable VITE_API_BASE_URL.");
  }
  return raw.trim().replace(/\/+$/, "");
}

// Query strings end up in browser history, proxy and server logs: never put credentials or personal data there.
const SENSITIVE_KEY = /pass|token|secret|email|e-mail|note|body|name|reason|key|auth|session/i;
const EMAIL_LIKE = /[^\s@]+@[^\s@]+/;

export function buildQuery(query: Query | undefined): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    const text = String(value);
    if (SENSITIVE_KEY.test(key) || EMAIL_LIKE.test(text)) {
      throw new ApiError(0, `Sensitive data cannot be sent in a search or filter (parameter "${key}").`);
    }
    params.set(key, text);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

type UnauthorizedHandler = () => void | Promise<void>;

async function defaultUnauthorizedHandler(): Promise<void> {
  try {
    await supabase.auth.signOut({ scope: "local" });
  } finally {
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.assign("/login");
    }
  }
}

let onUnauthorized: UnauthorizedHandler = defaultUnauthorizedHandler;

/** Test hook / app hook to override what happens on HTTP 401. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler ?? defaultUnauthorizedHandler;
}

/** Re-authentication prompt for 401 step_up_required; resolves true when the user re-authenticated. */
export type StepUpHandler = () => Promise<boolean>;
let onStepUp: StepUpHandler | null = null;

export function setStepUpHandler(handler: StepUpHandler | null): void {
  onStepUp = handler;
}

type DegradedHandler = (err: ApiError) => void;
let onDegraded: DegradedHandler | null = null;

/** Called for every error whose code says the system is degraded (drives the degraded-mode banner). */
export function setDegradedHandler(handler: DegradedHandler | null): void {
  onDegraded = handler;
}

export function isStepUpChallenge(status: number, code: string | null, wwwAuthenticate: string | null): boolean {
  return status === 401 && (code === "step_up_required" || /step_up_required/.test(wwwAuthenticate ?? ""));
}

function isFieldErrorList(value: unknown): value is FieldError[] {
  return (
    Array.isArray(value) &&
    value.every((v) => typeof v === "object" && v !== null && typeof (v as FieldError).field === "string")
  );
}

async function toApiError(res: Response, fallbackRequestId: string): Promise<ApiError> {
  let message = res.status >= 500 ? "The service is temporarily unavailable. Please try again." : "The request failed.";
  let fields: FieldError[] = [];
  let requestId: string | null = res.headers.get("X-Request-Id") ?? fallbackRequestId;
  let code: string | null = null;
  let degraded = false;
  try {
    const data: unknown = await res.json();
    if (typeof data === "object" && data !== null) {
      const obj = data as Record<string, unknown>;
      if (typeof obj.error === "string" && obj.error) message = obj.error;
      if (isFieldErrorList(obj.fields)) {
        fields = obj.fields.map((f) => ({ field: String(f.field), message: String(f.message ?? "Invalid value") }));
      }
      if (typeof obj.request_id === "string") requestId = obj.request_id;
      if (typeof obj.code === "string" && /^[a-z_]{1,64}$/.test(obj.code)) code = obj.code;
      if (obj.degraded === true) degraded = true;
    }
  } catch {
    // non-JSON error body: keep the generic message
  }
  if (isStepUpChallenge(res.status, code, res.headers.get("WWW-Authenticate"))) {
    code = "step_up_required";
    message = "Please confirm your identity again to continue.";
  } else if (res.status === 401) {
    message = "Your session has ended. Please sign in again.";
  }
  if (res.status === 403 && message === "The request failed.") message = "You do not have permission to perform this action.";
  return new ApiError(res.status, message, fields, requestId, code, degraded);
}

async function authHeaders(accept: string): Promise<{ headers: Headers; requestId: string }> {
  const requestId = newRequestId();
  const headers = new Headers({ Accept: accept, "X-Request-Id": requestId });
  const token = await getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { headers, requestId };
}

/** Shared error path: step-up retry (once), sign-out on any other 401, degraded-mode notification. */
async function handleFailure<T>(res: Response, requestId: string, retry: (() => Promise<T>) | null): Promise<T> {
  const error = await toApiError(res, requestId);
  if (error.code === "step_up_required") {
    // Highly sensitive action: re-authenticate (never sign out) and retry exactly once.
    if (retry && onStepUp && (await onStepUp())) return retry();
    throw error;
  }
  if (res.status === 401) await onUnauthorized();
  if (isDegradedError(error)) onDegraded?.(error);
  throw error;
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  if (!path.startsWith("/v1/")) throw new Error("API paths must start with /v1/.");
  const url = `${apiBaseUrl()}${path}${buildQuery(opts.query)}`;
  const { headers, requestId } = await authHeaders("application/json");

  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form; // browser sets the multipart boundary
  } else if (opts.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.body);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 20_000);
  const onAbort = () => controller.abort();
  opts.signal?.addEventListener("abort", onAbort);

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body,
      signal: controller.signal,
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "strict-origin-when-cross-origin",
    });
  } catch (err) {
    if (opts.signal?.aborted) throw err;
    throw new ApiError(0, "Unable to reach the server. Check your connection and try again.", [], requestId);
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onAbort);
  }

  if (!res.ok) {
    const retry = opts.stepUpRetried ? null : () => request<T>(method, path, { ...opts, stepUpRetried: true });
    return handleFailure<T>(res, requestId, retry);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const enc = encodeURIComponent;

export interface PatientFilters {
  q?: string;
  ward_id?: string;
  alarming?: boolean;
  limit?: number;
  offset?: number;
}

/** Drop undefined/empty keys: the API forbids unknown fields and empty filters carry no meaning. */
export function compact<T extends object>(obj: T): Partial<T> {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== "")) as Partial<T>;
}

function items<T>(page: Page<T>): T[] {
  return page.items;
}

/** Full JSON personal-data export (T740); the shape is defined by the API ("acme-clinical-personal-data/v1"). */
export type PersonalDataExport = Record<string, unknown> & { format: string; exported_at: string };

/** CSV export (T157): fetched with the bearer token (never a token in the URL) and saved as a file. */
async function downloadCsv(kind: ReportKind, f: { ward_id?: string; hours?: number }): Promise<void> {
  const url = `${apiBaseUrl()}/v1/reports/export.csv${buildQuery({ kind, ...f })}`;
  const { headers, requestId } = await authHeaders("text/csv");
  let res: Response;
  try {
    res = await fetch(url, { method: "GET", headers, credentials: "omit", cache: "no-store", redirect: "error" });
  } catch {
    throw new ApiError(0, "Unable to reach the server. Check your connection and try again.", [], requestId);
  }
  if (!res.ok) return handleFailure<void>(res, requestId, null);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = `${kind}.csv`;
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

export const MIN_PAIRING_CODE = 16;
export const MAX_PAIRING_CODE = 256;
/** Mirrors the API's pairing_code pattern. */
export const PAIRING_CODE_PATTERN = /^[A-Za-z0-9_-]{16,256}$/;

export const api = {
  // identity / session
  me: () => request<Me>("GET", "/v1/me"),
  updateMe: (full_name: string) => request<Me>("PATCH", "/v1/me", { body: { full_name } }),
  acceptPrivacyNotice: (notice_version: string) =>
    request<void>("POST", "/v1/me/privacy-notice", { body: { notice_version } }),
  exportMyData: (reauthentication: string) =>
    request<PersonalDataExport>("POST", "/v1/me/export", { body: { reauthentication } }),
  requestErasure: (reauthentication: string, confirm_text: string) =>
    request<ErasureRequest>("POST", "/v1/me/erasure-request", { body: { reauthentication, confirm_text } }),
  startSession: () => request<SessionStart>("POST", "/v1/auth/session"),
  logout: () => request<void>("POST", "/v1/auth/logout"),

  // wards / patients
  wards: () => request<Page<Ward>>("GET", "/v1/wards").then(items),
  beds: (wardId: string) => request<Page<Bed>>("GET", `/v1/wards/${enc(wardId)}/beds`).then(items),
  // POST: the search term (possibly a patient name) never travels in the URL (T219).
  patients: (f: PatientFilters = {}) => request<Page<Patient>>("POST", "/v1/patients/search", { body: compact(f) }),
  patient: (id: string) => request<Patient>("GET", `/v1/patients/${enc(id)}`),
  readings: (id: string, limit = 60) =>
    request<Page<Reading>>("GET", `/v1/patients/${enc(id)}/readings`, { query: { limit } }).then(items),
  observations: (id: string) => request<Page<Observation>>("GET", `/v1/patients/${enc(id)}/observations`).then(items),
  addObservation: (id: string, body: string) =>
    request<Observation>("POST", `/v1/patients/${enc(id)}/observations`, { body: { body } }),

  // files
  files: (patientId: string) => request<Page<Attachment>>("GET", `/v1/files/patients/${enc(patientId)}`).then(items),
  uploadFile: (patientId: string, file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<Attachment>("POST", `/v1/files/patients/${enc(patientId)}`, { form, timeoutMs: 60_000 });
  },
  fileUrl: (attachmentId: string) => request<SignedUrl>("GET", `/v1/files/${enc(attachmentId)}/url`),

  // alarms / thresholds
  alarms: (f: { state?: "active" | "resolved" | "all"; ward_id?: string; limit?: number } = {}) =>
    request<Page<Alarm>>("GET", "/v1/alarms", { query: { ...f } }).then(items),
  monitorStates: () => request<Page<MonitorState>>("GET", "/v1/alarms/monitor-states").then(items),
  systemStatus: () => request<SystemStatus>("GET", "/v1/alarms/system-status", { timeoutMs: 5000 }),
  acknowledgeAlarm: (id: string, note: string | null) =>
    request<AlarmAckResult>("POST", `/v1/alarms/${enc(id)}/acknowledge`, {
      body: { acknowledged: true, note: note || null },
    }),
  thresholds: (f: { ward_id?: string; patient_id?: string }) =>
    request<Page<Threshold>>("GET", "/v1/thresholds", { query: { ...f } }).then(items),
  setWardThreshold: (wardId: string, body: ThresholdUpdate) =>
    request<Threshold>("PUT", `/v1/thresholds/wards/${enc(wardId)}`, { body }),
  setPatientThreshold: (patientId: string, body: ThresholdUpdate) =>
    request<Threshold>("PUT", `/v1/thresholds/patients/${enc(patientId)}`, { body }),

  // devices
  monitors: () => request<Page<Monitor>>("GET", "/v1/monitors").then(items),
  assignMonitor: (monitorId: string, bedId: string, pairingCode: string) =>
    request<Monitor>("POST", `/v1/monitors/${enc(monitorId)}/assignment`, {
      body: { bed_id: bedId, confirm: true, pairing_code: pairingCode },
    }),
  unassignMonitor: (monitorId: string) => request<void>("DELETE", `/v1/monitors/${enc(monitorId)}/assignment`),
  maintenance: (monitorId: string) =>
    request<Page<MaintenanceRecord>>("GET", `/v1/monitors/${enc(monitorId)}/maintenance`).then(items),
  addMaintenance: (monitorId: string, body: MaintenanceIn) =>
    request<MaintenanceRecord>("POST", `/v1/monitors/${enc(monitorId)}/maintenance`, { body }),

  // reports
  wardActivity: (f: { ward_id?: string; hours?: number }) =>
    request<WardReport>("GET", "/v1/reports/ward-activity", { query: { ...f } }),
  exportCsv: (kind: ReportKind, f: { ward_id?: string; hours?: number } = {}) => downloadCsv(kind, f),

  // staff
  staff: () => request<Page<Staff>>("GET", "/v1/staff").then(items),
  inviteStaff: (body: StaffInvite) => request<InviteAccepted>("POST", "/v1/staff", { body }),
  updateStaff: (userId: string, body: StaffUpdate) => request<Staff>("PATCH", `/v1/staff/${enc(userId)}`, { body }),
  roleRequests: () => request<Page<RoleRequest>>("GET", "/v1/staff/role-requests").then(items),
  requestRoleChange: (userId: string, new_role: Role) =>
    request<RoleRequest>("POST", `/v1/staff/${enc(userId)}/role-requests`, { body: { new_role } }),
  approveRoleRequest: (requestId: string) => request<Staff>("POST", `/v1/staff/role-requests/${enc(requestId)}/approve`),

  // settings
  securitySettings: () => request<SecuritySettings>("GET", "/v1/settings/security"),
  updateSecuritySettings: (body: SecuritySettingsUpdate) =>
    request<SecuritySettings>("PATCH", "/v1/settings/security", { body }),

  // simulation
  simulation: () => request<SimulationState>("GET", "/v1/simulation"),
  setScenario: (scenario: Scenario, monitor_ids: string[] = []) =>
    request<SimulationActionResult>("POST", "/v1/simulation/scenario", {
      body: { scenario, monitor_ids, acknowledged: true },
    }),
  advanceSimulation: (steps: number, expected_version: number) =>
    request<AdvanceResult>("POST", "/v1/simulation/advance", { body: { steps, expected_version } }),
  resetSimulation: (confirm_text: string) =>
    request<SimulationActionResult>("POST", "/v1/simulation/reset", { body: { confirm_text, acknowledged: true } }),

  // events
  events: (f: { action?: string; entity_type?: string; before_id?: number; limit?: number } = {}) =>
    request<Page<EventRecord>>("GET", "/v1/events", { query: { ...f } }).then(items),
  eventsIntegrity: () => request<IntegrityResult>("GET", "/v1/events/integrity"),

  // break glass
  requestBreakGlass: (patient_id: string, reason: string) =>
    request<BreakGlassGrant>("POST", "/v1/break-glass", { body: { patient_id, reason, acknowledged_warning: true } }),
  myBreakGlass: () => request<{ items: ActiveGrant[] }>("GET", "/v1/break-glass/mine").then((r) => r.items),
  pendingBreakGlass: () => request<{ items: PendingGrant[] }>("GET", "/v1/break-glass/pending").then((r) => r.items),
  revokeBreakGlass: (grantId: string) => request<void>("POST", `/v1/break-glass/${enc(grantId)}/revoke`),
  reviewBreakGlass: (grantId: string, outcome: BreakGlassOutcome) =>
    request<void>("POST", `/v1/break-glass/${enc(grantId)}/review`, { body: { outcome } }),
};

/** User-facing text for any thrown value (never leaks stack traces). */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.name === "AbortError") return "The request was cancelled.";
  return "Something went wrong. Please try again.";
}
