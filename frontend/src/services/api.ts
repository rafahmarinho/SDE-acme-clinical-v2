// Typed client for the ACME Clinical API (FastAPI).
// * Attaches the Supabase access token as a Bearer token; no cookies (credentials: "omit").
// * Sends JSON bodies; query strings carry only ids/filters (guarded below).
// * Generates an X-Request-Id per call and maps errors to the API's {error, fields?, request_id} shape.
// * 401 => local sign-out and redirect to /login.
import { getAccessToken, supabase } from "../lib/supabase";
import type {
  Alarm,
  Attachment,
  BreakGlassGrant,
  EventRecord,
  IntegrityResult,
  MaintenanceIn,
  MaintenanceRecord,
  Me,
  Monitor,
  Observation,
  Page,
  Patient,
  ProfileExport,
  Reading,
  Scenario,
  SecuritySettings,
  SecuritySettingsUpdate,
  SessionStart,
  SignedUrl,
  SimulationState,
  Staff,
  StaffInvite,
  StaffUpdate,
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

  constructor(status: number, message: string, fields: FieldError[] = [], requestId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
    this.requestId = requestId;
  }
}

export type QueryValue = string | number | boolean | null | undefined;
export type Query = Record<string, QueryValue>;

interface RequestOptions {
  query?: Query;
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  timeoutMs?: number;
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
  try {
    const data: unknown = await res.json();
    if (typeof data === "object" && data !== null) {
      const obj = data as Record<string, unknown>;
      if (typeof obj.error === "string" && obj.error) message = obj.error;
      if (isFieldErrorList(obj.fields)) {
        fields = obj.fields.map((f) => ({ field: String(f.field), message: String(f.message ?? "Invalid value") }));
      }
      if (typeof obj.request_id === "string") requestId = obj.request_id;
    }
  } catch {
    // non-JSON error body: keep the generic message
  }
  if (res.status === 401) message = "Your session has ended. Please sign in again.";
  if (res.status === 403 && message === "The request failed.") message = "You do not have permission to perform this action.";
  return new ApiError(res.status, message, fields, requestId);
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  if (!path.startsWith("/v1/")) throw new Error("API paths must start with /v1/.");
  const url = `${apiBaseUrl()}${path}${buildQuery(opts.query)}`;
  const requestId = newRequestId();
  const headers = new Headers({ Accept: "application/json", "X-Request-Id": requestId });
  const token = await getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

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
    const error = await toApiError(res, requestId);
    if (res.status === 401) await onUnauthorized();
    throw error;
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

export const api = {
  // identity / session
  me: () => request<Me>("GET", "/v1/me"),
  updateMe: (full_name: string) => request<Me>("PATCH", "/v1/me", { body: { full_name } }),
  acceptPrivacyNotice: () => request<void>("POST", "/v1/me/privacy-notice"),
  exportMyData: () => request<ProfileExport>("GET", "/v1/me/export"),
  startSession: () => request<SessionStart>("POST", "/v1/auth/session"),
  logout: () => request<void>("POST", "/v1/auth/logout"),

  // wards / patients
  wards: () => request<Ward[]>("GET", "/v1/wards"),
  patients: (f: PatientFilters = {}) => request<Page<Patient>>("GET", "/v1/patients", { query: { ...f } }),
  patient: (id: string) => request<Patient>("GET", `/v1/patients/${enc(id)}`),
  readings: (id: string, limit = 60) =>
    request<Reading[]>("GET", `/v1/patients/${enc(id)}/readings`, { query: { limit } }),
  observations: (id: string) => request<Observation[]>("GET", `/v1/patients/${enc(id)}/observations`),
  addObservation: (id: string, body: string) =>
    request<Observation>("POST", `/v1/patients/${enc(id)}/observations`, { body: { body } }),

  // files
  files: (patientId: string) => request<Attachment[]>("GET", `/v1/files/patients/${enc(patientId)}`),
  uploadFile: (patientId: string, file: File) => {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<Attachment>("POST", `/v1/files/patients/${enc(patientId)}`, { form, timeoutMs: 60_000 });
  },
  fileUrl: (attachmentId: string) => request<SignedUrl>("GET", `/v1/files/${enc(attachmentId)}/url`),

  // alarms / thresholds
  alarms: (f: { state?: "active" | "resolved" | "all"; ward_id?: string; limit?: number } = {}) =>
    request<Alarm[]>("GET", "/v1/alarms", { query: { ...f } }),
  acknowledgeAlarm: (id: string, note: string | null) =>
    request<Alarm>("POST", `/v1/alarms/${enc(id)}/acknowledge`, { body: { note: note || null } }),
  thresholds: (f: { ward_id?: string; patient_id?: string }) =>
    request<Threshold[]>("GET", "/v1/thresholds", { query: { ...f } }),
  setWardThreshold: (wardId: string, body: ThresholdUpdate) =>
    request<Threshold>("PUT", `/v1/thresholds/wards/${enc(wardId)}`, { body }),
  setPatientThreshold: (patientId: string, body: ThresholdUpdate) =>
    request<Threshold>("PUT", `/v1/thresholds/patients/${enc(patientId)}`, { body }),

  // devices
  monitors: () => request<Monitor[]>("GET", "/v1/monitors"),
  assignMonitor: (monitorId: string, bedId: string) =>
    request<Monitor>("POST", `/v1/monitors/${enc(monitorId)}/assignment`, { body: { bed_id: bedId, confirm: true } }),
  unassignMonitor: (monitorId: string) => request<void>("DELETE", `/v1/monitors/${enc(monitorId)}/assignment`),
  maintenance: (monitorId: string) =>
    request<MaintenanceRecord[]>("GET", `/v1/monitors/${enc(monitorId)}/maintenance`),
  addMaintenance: (monitorId: string, body: MaintenanceIn) =>
    request<MaintenanceRecord>("POST", `/v1/monitors/${enc(monitorId)}/maintenance`, { body }),

  // reports
  wardActivity: (f: { ward_id?: string; hours?: number }) =>
    request<WardReport>("GET", "/v1/reports/ward-activity", { query: { ...f } }),

  // staff
  staff: () => request<Staff[]>("GET", "/v1/staff"),
  inviteStaff: (body: StaffInvite) => request<Staff>("POST", "/v1/staff", { body }),
  updateStaff: (userId: string, body: StaffUpdate) => request<Staff>("PATCH", `/v1/staff/${enc(userId)}`, { body }),

  // settings
  securitySettings: () => request<SecuritySettings>("GET", "/v1/settings/security"),
  updateSecuritySettings: (body: SecuritySettingsUpdate) =>
    request<SecuritySettings>("PATCH", "/v1/settings/security", { body }),

  // simulation
  simulation: () => request<SimulationState>("GET", "/v1/simulation"),
  setScenario: (scenario: Scenario, monitor_ids: string[] = []) =>
    request<SimulationState>("POST", "/v1/simulation/scenario", { body: { scenario, monitor_ids } }),
  advanceSimulation: (steps: number, expected_version: number) =>
    request<Record<string, unknown>>("POST", "/v1/simulation/advance", { body: { steps, expected_version } }),
  resetSimulation: (confirm_text: string) =>
    request<SimulationState>("POST", "/v1/simulation/reset", { body: { confirm_text } }),

  // events
  events: (f: { action?: string; entity_type?: string; before_id?: number; limit?: number } = {}) =>
    request<EventRecord[]>("GET", "/v1/events", { query: { ...f } }),
  eventsIntegrity: () => request<IntegrityResult>("GET", "/v1/events/integrity"),

  // break glass
  requestBreakGlass: (patient_id: string, reason: string) =>
    request<BreakGlassGrant>("POST", "/v1/break-glass", { body: { patient_id, reason } }),
};

/** User-facing text for any thrown value (never leaks stack traces). */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.name === "AbortError") return "The request was cancelled.";
  return "Something went wrong. Please try again.";
}
