// Permission-driven UI gating. This is UX only: every API route enforces the same permission server-side.
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import type { Permission } from "../services/types";
import { LoadingState } from "./LoadingState";

export interface NavItem {
  to: string;
  label: string;
  /** All listed permissions are required; empty = any signed-in user. */
  requires: Permission[];
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/wards", label: "Wards", requires: ["alarm:read"] },
  { to: "/patients", label: "Patients", requires: ["patient:read"] },
  { to: "/live", label: "Live monitoring", requires: ["patient:read", "alarm:read"] },
  { to: "/alarms", label: "Alarms", requires: ["alarm:read"] },
  { to: "/devices", label: "Devices", requires: ["device:read"] },
  { to: "/thresholds", label: "Thresholds", requires: ["alarm:read"] },
  { to: "/reports", label: "Reports", requires: ["report:read"] },
  { to: "/team", label: "Team", requires: ["staff:manage"] },
  { to: "/simulation", label: "Simulation", requires: ["simulation:control"] },
  { to: "/events", label: "Events", requires: [] },
  { to: "/settings", label: "Settings", requires: ["settings:manage"] },
  { to: "/profile", label: "Profile", requires: [] },
];

export function hasAll(perms: readonly string[] | undefined, required: readonly Permission[]): boolean {
  if (!perms) return false;
  return required.every((p) => perms.includes(p));
}

export function visibleNavItems(perms: readonly string[] | undefined): NavItem[] {
  return NAV_ITEMS.filter((item) => hasAll(perms, item.requires));
}

/** First screen a user can open (used after sign-in). */
export function homePathFor(perms: readonly string[] | undefined): string {
  return visibleNavItems(perms)[0]?.to ?? "/profile";
}

interface RoleGuardProps {
  requires: Permission[];
  children: ReactNode;
  /** Rendered when permissions are missing; defaults to nothing (hide). */
  fallback?: ReactNode;
}

/** Inline guard: renders children only if the signed-in user holds every required permission. */
export function RoleGuard({ requires, children, fallback = null }: RoleGuardProps) {
  const { me } = useAuth();
  return <>{hasAll(me?.permissions, requires) ? children : fallback}</>;
}

/** Screens reachable while the privacy notice still awaits acknowledgement. */
export const PRIVACY_GATE_EXEMPT: readonly string[] = ["/profile", "/privacy"];

/** Route guard: requires a signed-in user with a loaded profile, plus optional permissions. */
export function RequireAuth({ requires = [], children }: { requires?: Permission[]; children: ReactNode }) {
  const { status, me } = useAuth();
  const location = useLocation();
  if (status === "loading") return <LoadingState label="Loading your session…" />;
  if (status !== "signed_in" || !me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  // Privacy notice before use (T239/T751): until the current notice is acknowledged, only /profile opens.
  if (me.privacy_notice_required === true && !PRIVACY_GATE_EXEMPT.includes(location.pathname)) {
    return <Navigate to="/profile" replace state={{ from: location.pathname }} />;
  }
  if (!hasAll(me.permissions, requires)) {
    return (
      <section className="card" role="alert">
        <h1>Not available</h1>
        <p>Your role does not include access to this screen.</p>
      </section>
    );
  }
  return <>{children}</>;
}
