import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

vi.mock("../lib/supabase", () => ({
  getAccessToken: vi.fn(async () => null),
  supabase: { auth: {} },
  SUPABASE_URL: "https://example.supabase.co",
}));

import { AuthContext, type AuthState } from "../auth/AuthContext";
import { Navigation } from "../App";
import { RoleGuard } from "./RoleGuard";
import type { Me, Permission, Role } from "../services/types";

// Mirrors backend/app/core/security.py PERMISSIONS.
const PERMS: Record<Role, Permission[]> = {
  nurse: ["patient:read", "observation:write", "alarm:read", "alarm:ack", "device:read", "file:write", "break_glass:request"],
  physician: [
    "patient:read", "observation:write", "alarm:read", "alarm:ack", "threshold:write", "device:read", "report:read",
    "file:write", "break_glass:request",
  ],
  biomed_tech: ["alarm:read", "device:read", "device:write", "maintenance:write"],
  admin: [
    "patient:read", "alarm:read", "device:read", "device:write", "threshold:write", "report:read", "staff:manage",
    "settings:manage", "simulation:control", "events:read_all", "break_glass:review",
  ],
};

function authFor(role: Role): AuthState {
  const me: Me = {
    user_id: "00000000-0000-4000-8000-000000000001",
    email: `${role}@acme.test`,
    full_name: `Test ${role}`,
    role,
    ward_ids: [],
    permissions: PERMS[role],
    previous_login_at: null,
    privacy_notice_accepted_at: null,
    session_idle_minutes: 15,
  };
  return {
    status: "signed_in",
    session: null,
    me,
    error: null,
    loginNotice: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    refreshMe: vi.fn(),
    dismissLoginNotice: vi.fn(),
    can: (p) => me.permissions.includes(p),
  };
}

function renderAs(role: Role, ui: ReactNode) {
  return render(
    <AuthContext.Provider value={authFor(role)}>
      <MemoryRouter>{ui}</MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("role-aware navigation", () => {
  it("hides admin navigation for nurses", () => {
    renderAs("nurse", <Navigation />);
    expect(screen.queryByRole("link", { name: "Team" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Simulation" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Reports" })).toBeNull();
    expect(screen.getByRole("link", { name: "Patients" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Alarms" })).toBeTruthy();
  });

  it("shows admin navigation for administrators", () => {
    renderAs("admin", <Navigation />);
    expect(screen.getByRole("link", { name: "Team" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Simulation" })).toBeTruthy();
  });

  it("hides patient screens from biomedical technicians", () => {
    renderAs("biomed_tech", <Navigation />);
    expect(screen.queryByRole("link", { name: "Patients" })).toBeNull();
    expect(screen.getByRole("link", { name: "Devices" })).toBeTruthy();
  });

  it("RoleGuard renders children only with every required permission", () => {
    renderAs(
      "nurse",
      <>
        <RoleGuard requires={["settings:manage"]}>
          <span>admin-only</span>
        </RoleGuard>
        <RoleGuard requires={["alarm:ack"]}>
          <span>ack-button</span>
        </RoleGuard>
      </>,
    );
    expect(screen.queryByText("admin-only")).toBeNull();
    expect(screen.getByText("ack-button")).toBeTruthy();
  });
});
