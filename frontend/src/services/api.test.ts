import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/supabase", () => ({
  getAccessToken: vi.fn(async () => "test-access-token"),
  supabase: { auth: { signOut: vi.fn(async () => ({ error: null })) } },
  SUPABASE_URL: "https://example.supabase.co",
}));

import {
  ApiError,
  api,
  buildQuery,
  isDegradedError,
  request,
  setDegradedHandler,
  setStepUpHandler,
  setUnauthorizedHandler,
} from "./api";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("api client", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setUnauthorizedHandler(null);
    setStepUpHandler(null);
    setDegradedHandler(null);
  });

  it("attaches the bearer token, a request id and JSON content type", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { full_name: "Ana" }));
    await api.updateMe("Ana");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0]!;
    const headers = new Headers(init?.headers);
    expect(String(url)).toBe("https://api.example.test/v1/me");
    expect(headers.get("Authorization")).toBe("Bearer test-access-token");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-Request-Id")).toMatch(/^[A-Za-z0-9-]{8,64}$/);
    expect(init?.method).toBe("PATCH");
    expect(init?.credentials).toBe("omit");
    expect(init?.body).toBe(JSON.stringify({ full_name: "Ana" }));
  });

  it("never puts the token, emails or passwords in the URL", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { email: "new.nurse@acme.test" }));
    await api.inviteStaff({ email: "new.nurse@acme.test", full_name: "New Nurse", role: "nurse", ward_ids: [] });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("https://api.example.test/v1/staff");
    expect(String(url)).not.toContain("?");
    expect(String(url)).not.toContain("test-access-token");
    expect(String(init?.body)).toContain("new.nurse@acme.test");
  });

  it("refuses sensitive query parameters and email-like values", () => {
    expect(() => buildQuery({ password: "hunter2" })).toThrow(ApiError);
    expect(() => buildQuery({ email: "a@b.test" })).toThrow(ApiError);
    expect(() => buildQuery({ access_token: "x" })).toThrow(ApiError);
    expect(() => buildQuery({ q: "someone@acme.test" })).toThrow(ApiError);
    expect(buildQuery({ ward_id: "8b4c4b8e-0000-4000-8000-000000000001", alarming: true, q: undefined })).toBe(
      "?ward_id=8b4c4b8e-0000-4000-8000-000000000001&alarming=true",
    );
  });

  it("searches patients with a POST body, never a query string (T219)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [], next_offset: null }));
    await api.patients({ q: "Doe", alarming: true, limit: 25, offset: 0, ward_id: undefined });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("https://api.example.test/v1/patients/search");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ q: "Doe", alarming: true, limit: 25, offset: 0 });
  });

  it("unwraps {items, next_offset} list envelopes", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [{ id: "w1" }], next_offset: null }));
    await expect(api.wards()).resolves.toEqual([{ id: "w1" }]);
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [{ id: "b1", occupied: false }], next_offset: null }));
    await expect(api.beds("w1")).resolves.toEqual([{ id: "b1", occupied: false }]);
    expect(String(fetchMock.mock.calls[1]![0])).toBe("https://api.example.test/v1/wards/w1/beds");
  });

  it("sends the device pairing code when binding a monitor (T425)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { id: "m1" }));
    await api.assignMonitor("m1", "b1", "pairing-code-0123456789");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("https://api.example.test/v1/monitors/m1/assignment");
    expect(JSON.parse(String(init?.body))).toEqual({ bed_id: "b1", confirm: true, pairing_code: "pairing-code-0123456789" });
  });

  it("sends the explicit confirmations critical actions require (T342)", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(200, { notice: "n" }));
    await api.acknowledgeAlarm("a1", "");
    await api.resetSimulation("RESET DEMO DATA");
    await api.requestBreakGlass("p1", "Cardiac arrest in corridor");
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse(String(init?.body)));
    expect(bodies[0]).toEqual({ acknowledged: true, note: null });
    expect(bodies[1]).toEqual({ confirm_text: "RESET DEMO DATA", acknowledged: true });
    expect(bodies[2]).toMatchObject({ patient_id: "p1", acknowledged_warning: true });
  });

  it("maps API errors to {error, fields, request_id}", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, { error: "Invalid request.", fields: [{ field: "body", message: "Too long" }], request_id: "req-12345678" }),
    );
    const err = await request("POST", "/v1/patients/x/observations", { body: { body: "x" } }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    const apiErr = err as ApiError;
    expect(apiErr.status).toBe(422);
    expect(apiErr.message).toBe("Invalid request.");
    expect(apiErr.fields).toEqual([{ field: "body", message: "Too long" }]);
    expect(apiErr.requestId).toBe("req-12345678");
  });

  it("signs out locally on 401", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetchMock.mockResolvedValue(jsonResponse(401, { error: "Authentication required.", request_id: "req-abcdefgh" }));
    await expect(api.me()).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not set a JSON content type for multipart uploads", async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { id: "1" }));
    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "scan.pdf", { type: "application/pdf" });
    await api.uploadFile("p1", file);
    const init = fetchMock.mock.calls[0]![1];
    expect(new Headers(init?.headers).get("Content-Type")).toBeNull();
    expect(init?.body).toBeInstanceOf(FormData);
  });

  it("parses the error code and flags degraded-mode errors", async () => {
    const degraded = vi.fn();
    setDegradedHandler(degraded);
    fetchMock.mockResolvedValue(
      jsonResponse(503, { error: "Live monitoring data is temporarily unavailable.", code: "monitoring_unavailable", degraded: true, request_id: "req-12345678" }),
    );
    const err = (await api.alarms().catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("monitoring_unavailable");
    expect(isDegradedError(err)).toBe(true);
    expect(degraded).toHaveBeenCalledTimes(1);
  });

  it("step-up challenge: re-authenticates and retries once, never signs out", async () => {
    const signOut = vi.fn();
    const stepUp = vi.fn(async () => true);
    setUnauthorizedHandler(signOut);
    setStepUpHandler(stepUp);
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse(401, { error: "Please confirm", code: "step_up_required" }, { "WWW-Authenticate": 'Bearer error_description="step_up_required"' }),
      )
      .mockResolvedValueOnce(jsonResponse(200, { notice: "done", scenario: "normal" }));
    await expect(api.resetSimulation("RESET DEMO DATA")).resolves.toMatchObject({ notice: "done" });
    expect(stepUp).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(signOut).not.toHaveBeenCalled();
  });

  it("step-up challenge: cancelled or repeated challenges fail without a retry loop", async () => {
    const signOut = vi.fn();
    setUnauthorizedHandler(signOut);
    setStepUpHandler(async () => false);
    fetchMock.mockImplementation(async () => jsonResponse(401, { error: "x", code: "step_up_required" }));
    await expect(api.updateStaff("u1", { is_active: false })).rejects.toMatchObject({ status: 401, code: "step_up_required" });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockClear();
    setStepUpHandler(async () => true);
    await expect(api.updateStaff("u1", { is_active: false })).rejects.toMatchObject({ code: "step_up_required" });
    expect(fetchMock).toHaveBeenCalledTimes(2); // original + exactly one retry
    expect(signOut).not.toHaveBeenCalled();
  });

  it("recognises the challenge from WWW-Authenticate alone", async () => {
    setStepUpHandler(async () => false);
    fetchMock.mockResolvedValue(
      jsonResponse(401, { error: "Please confirm" }, { "WWW-Authenticate": 'Bearer error="insufficient_user_authentication", error_description="step_up_required"' }),
    );
    await expect(api.setWardThreshold("w1", { parameter: "spo2", low_limit: 90, high_limit: 100, confirm: true })).rejects.toMatchObject({
      code: "step_up_required",
    });
  });
});
