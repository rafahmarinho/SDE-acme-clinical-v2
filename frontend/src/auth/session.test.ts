import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  request: vi.fn(async () => undefined),
  signOut: vi.fn(async () => ({ error: null })),
  removeAllChannels: vi.fn(async () => []),
}));

vi.mock("../lib/supabase", () => ({
  supabase: { auth: { signOut: mocks.signOut }, removeAllChannels: mocks.removeAllChannels },
}));
vi.mock("../services/api", () => ({ request: mocks.request }));

import { clearBrowserData, performLogout, signedOutMessage, takeSignedOutReason, rememberSignedOutReason, signedOutPath } from "./session";

const TOKEN_KEY = "sb-example-auth-token";

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify({ access_token: "eyJ.a.b", refresh_token: "r" }));
  sessionStorage.setItem("acme.patientCache", "Maria Silva");
  localStorage.setItem("acme.ui-cache", "{\"ward\":\"ICU\"}");
  document.cookie = "acme_pref=1; path=/";
});
afterEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

describe("performLogout (T26/T93/T1540)", () => {
  it("revokes server-side, stops realtime, drops tokens, clears storage and replaces the location", async () => {
    const navigate = vi.fn();
    await performLogout({ reason: "user", navigate });
    expect(mocks.request).toHaveBeenCalledWith("POST", "/v1/auth/logout", expect.objectContaining({ body: undefined }));
    expect(mocks.removeAllChannels).toHaveBeenCalledOnce();
    expect(mocks.signOut).toHaveBeenCalledWith({ scope: "local" });
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(sessionStorage.getItem("acme.patientCache")).toBeNull();
    expect(localStorage.length).toBe(0);
    expect(document.cookie).toBe("");
    expect(navigate).toHaveBeenCalledWith("/signed-out?reason=user");
    expect(takeSignedOutReason()).toBe("user");
    expect(takeSignedOutReason()).toBeNull(); // shown once
  });

  it("sign out everywhere asks the API to revoke every session", async () => {
    await performLogout({ reason: "user", scope: "global", navigate: vi.fn() });
    expect(mocks.request).toHaveBeenCalledWith("POST", "/v1/auth/logout", expect.objectContaining({ body: { scope: "global" } }));
  });

  it("still clears the browser when the API is unreachable", async () => {
    mocks.request.mockRejectedValueOnce(new Error("offline"));
    const navigate = vi.fn();
    await performLogout({ reason: "idle", navigate });
    expect(mocks.signOut).toHaveBeenCalled();
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(navigate).toHaveBeenCalledWith("/signed-out?reason=idle");
  });

  it("does not call the API again after a 401 (session already ended server-side)", async () => {
    await performLogout({ reason: "revoked", notifyServer: false, navigate: vi.fn() });
    expect(mocks.request).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("concurrent triggers (idle + 401) share one logout", async () => {
    const navigate = vi.fn();
    await Promise.all([performLogout({ reason: "idle", navigate }), performLogout({ reason: "revoked", navigate })]);
    expect(navigate).toHaveBeenCalledOnce();
  });
});

describe("clearBrowserData", () => {
  it("removes every Web Storage key", async () => {
    await clearBrowserData();
    expect(sessionStorage.length).toBe(0);
    expect(localStorage.length).toBe(0);
  });
});

describe("signed-out messages", () => {
  it("explains idle, expiry and displacement by another device", () => {
    expect(signedOutMessage("idle")).toMatch(/inactivity/);
    expect(signedOutMessage("expired")).toMatch(/maximum duration/);
    expect(signedOutMessage("revoked")).toMatch(/another device/);
    expect(signedOutMessage(null)).toBeNull();
  });
});

describe("/signed-out hand-off (S2)", () => {
  it("re-stores only allow-listed reasons", () => {
    rememberSignedOutReason("idle");
    expect(takeSignedOutReason()).toBe("idle");
    rememberSignedOutReason("<script>");
    expect(takeSignedOutReason()).toBeNull();
    expect(signedOutPath("expired")).toBe("/signed-out?reason=expired");
  });
});
