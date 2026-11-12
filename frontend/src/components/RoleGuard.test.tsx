import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

vi.mock("../lib/supabase", () => ({
  getAccessToken: vi.fn(async () => null),
  supabase: { auth: {} },
  SUPABASE_URL: "https://example.supabase.co",
}));

import { AuthContext, type AuthState } from "../auth/AuthContext";
import { Navigation } from "../App";
import { RequireAuth, RoleGuard, visibleNavItems } from "./RoleGuard";
import type { Me, Permission, Role } from "../services/types";

// Mirrors backend/app/core/security.py PERMISSIONS.
const PERMS: Record<Role, Permission[]> = {
  nurse: ["patient:read", "observation:write", "alarm:read", "alarm:ack", "device:read", "file:write", "break_glass:request"],
  physician: [
    "patient:read", "observation:write", "alarm:read", "alarm:ack", "threshold:write", "device:read", "report:read",
    "file:write", "break_glass:request",
  ],
  biomed_tech: ["alarm:read", "device:read", "device:write", "maintenance:read", "maintenance:write"],
  admin: [
    "patient:read", "alarm:read", "device:read", "device:write", "maintenance:read", "report:read", "staff:manage",
    "settings:manage", "simulation:control", "events:read_all", "break_glass:review",
  ],
};

function authFor(role: Role, extra: Partial<Me> = {}): AuthState {
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
    ...extra,
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

describe("settings and privacy gating (P2/P3)", () => {
  it("Settings is visible only with settings:manage", () => {
    expect(visibleNavItems(PERMS.admin).some((i) => i.to === "/settings")).toBe(true);
    for (const role of ["nurse", "physician", "biomed_tech"] as Role[]) {
      expect(visibleNavItems(PERMS[role]).some((i) => i.to === "/settings")).toBe(false);
    }
  });

  it("the Settings route refuses roles without settings:manage", () => {
    render(
      <AuthContext.Provider value={authFor("nurse")}>
        <MemoryRouter>
          <RequireAuth requires={["settings:manage"]}>
            <p>settings-screen</p>
          </RequireAuth>
        </MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(screen.queryByText("settings-screen")).toBeNull();
    expect(screen.getByText(/Not available/)).toBeTruthy();
  });

  function renderAt(path: string, me: Partial<Me>) {
    return render(
      <AuthContext.Provider value={authFor("nurse", me)}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/patients" element={<RequireAuth><p>patients-screen</p></RequireAuth>} />
            <Route path="/profile" element={<RequireAuth><p>profile-screen</p></RequireAuth>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    );
  }

  it("redirects to /profile while the privacy notice is not acknowledged", () => {
    renderAt("/patients", { privacy_notice_required: true });
    expect(screen.queryByText("patients-screen")).toBeNull();
    expect(screen.getByText("profile-screen")).toBeTruthy();
  });

  it("opens screens normally once the notice is acknowledged", () => {
    renderAt("/patients", { privacy_notice_required: false });
    expect(screen.getByText("patients-screen")).toBeTruthy();
  });
});
