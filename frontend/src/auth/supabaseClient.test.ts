// T28/T95 (no remember-me: session ends with the browser), T27/T94 (PKCE, no tokens in URLs),
// T23/T1092 (no cookie storage for auth tokens).
import { describe, expect, it, vi } from "vitest";

const createClient = vi.hoisted(() => vi.fn(() => ({ auth: {} })));
vi.mock("@supabase/supabase-js", () => ({ createClient }));

import "../lib/supabase";

describe("Supabase browser client configuration", () => {
  const options = (createClient.mock.calls[0] as unknown[])[2] as {
    auth: { storage?: Storage; flowType?: string; detectSessionInUrl?: boolean; persistSession?: boolean };
    cookies?: unknown;
  };

  it("keeps the session in sessionStorage only (survives reload, not a browser restart)", () => {
    expect(options.auth.storage).toBe(window.sessionStorage);
    expect(options.auth.storage).not.toBe(window.localStorage);
    expect(options.cookies).toBeUndefined();
  });

  it("uses PKCE so recovery links carry a one-time code instead of tokens", () => {
    expect(options.auth.flowType).toBe("pkce");
    expect(options.auth.detectSessionInUrl).toBe(true);
  });
});
