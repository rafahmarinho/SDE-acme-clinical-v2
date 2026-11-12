// Device pairing (N3/T425) and suppressed report counts (P7).
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/supabase", () => ({
  getAccessToken: vi.fn(async () => null),
  supabase: { auth: {}, channel: vi.fn(), removeChannel: vi.fn() },
  SUPABASE_URL: "https://example.supabase.co",
}));

import { pairingCodeValid } from "./Devices";
import { formatCount } from "./Reports";

describe("pairing code", () => {
  it("accepts 16-256 URL-safe characters only", () => {
    expect(pairingCodeValid("abcDEF0123456789")).toBe(true);
    expect(pairingCodeValid("x".repeat(256))).toBe(true);
    expect(pairingCodeValid("short-code")).toBe(false);
    expect(pairingCodeValid("x".repeat(257))).toBe(false);
    expect(pairingCodeValid("abcdefghijklmnop qr")).toBe(false);
  });
});

describe("suppressed counts", () => {
  it("renders null (small count) as fewer than 5", () => {
    expect(formatCount(null)).toBe("fewer than 5");
    expect(formatCount(12)).toBe("12");
  });
});
