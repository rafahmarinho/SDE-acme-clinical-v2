import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/supabase", () => ({
  getAccessToken: vi.fn(async () => "test-access-token"),
  supabase: { auth: { signOut: vi.fn(async () => ({ error: null })) } },
  SUPABASE_URL: "https://example.supabase.co",
}));

import { ApiError, api, buildQuery, request, setUnauthorizedHandler } from "./api";

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

  it("sends only filters in query strings for list endpoints", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { items: [], next_offset: null }));
    await api.patients({ q: "Doe", alarming: true, limit: 25, offset: 0 });
    const url = new URL(String(fetchMock.mock.calls[0]![0]));
    expect(url.pathname).toBe("/v1/patients");
    expect([...url.searchParams.keys()].sort()).toEqual(["alarming", "limit", "offset", "q"]);
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
});
