// Unified security settings are administrator-only (T371/T2273).
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../lib/supabase", () => ({
  getAccessToken: vi.fn(async () => "token"),
  supabase: { auth: {} },
  SUPABASE_URL: "https://example.supabase.co",
}));

const requestMock = vi.fn(async () => new Promise(() => undefined));
const securitySettings = vi.fn(async () => new Promise(() => undefined));
vi.mock("../services/api", async (orig) => {
  const actual = await orig<typeof import("../services/api")>();
  return {
    ...actual,
    request: (...args: unknown[]) => requestMock(...(args as [])),
    api: { ...actual.api, securitySettings: () => securitySettings() },
  };
});

import { AuthContext, type AuthState } from "../auth/AuthContext";
import Settings from "./Settings";
import type { Me, Permission } from "../services/types";

function renderAs(perms: Permission[]) {
  const auth: AuthState = {
    status: "signed_in",
    session: null,
    me: { permissions: perms } as unknown as Me,
    error: null,
    loginNotice: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    refreshMe: vi.fn(),
    dismissLoginNotice: vi.fn(),
    can: (p) => perms.includes(p),
  };
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("security settings screen", () => {
  it.each([[["patient:read", "alarm:ack"]], [["device:write", "maintenance:write"]]] as Permission[][][])(
    "does not call the settings API for non-administrators (%j)",
    (perms) => {
      renderAs(perms);
      expect(screen.getByText(/managed by administrators/i)).toBeTruthy();
      expect(securitySettings).not.toHaveBeenCalled();
      expect(requestMock).not.toHaveBeenCalled();
    },
  );

  it("loads settings, configuration report, retention and erasure requests for administrators", () => {
    renderAs(["settings:manage", "staff:manage"]);
    expect(securitySettings).toHaveBeenCalled();
    const paths = requestMock.mock.calls.map((c) => (c as unknown[])[1]);
    expect(paths).toEqual(
      expect.arrayContaining(["/v1/settings/security/report", "/v1/settings/retention", "/v1/settings/privacy-requests"]),
    );
  });
});
