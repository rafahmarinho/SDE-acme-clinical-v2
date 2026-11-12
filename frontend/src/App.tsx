import { Suspense, lazy, useState, type ReactNode } from "react";
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useSearchParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { rememberSignedOutReason, signedOutMessage, takeSignedOutReason } from "./auth/session";
import { DegradedBanner } from "./components/DegradedBanner";
import { StepUpDialog } from "./components/StepUpDialog";
import { RequireAuth, homePathFor, visibleNavItems } from "./components/RoleGuard";
import { LoadingState } from "./components/LoadingState";
import { formatDateTime, humanize } from "./lib/format";
import type { Permission } from "./services/types";
import Login from "./screens/Login";
import ForgotPassword from "./screens/ForgotPassword";
import ResetPassword from "./screens/ResetPassword";

const Profile = lazy(() => import("./screens/Profile"));
const PrivacyPage = lazy(() => import("./screens/Profile").then((m) => ({ default: m.PrivacyPage })));
const Settings = lazy(() => import("./screens/Settings"));
const WardOverview = lazy(() => import("./screens/WardOverview"));
const PatientList = lazy(() => import("./screens/PatientList"));
const PatientDetail = lazy(() => import("./screens/PatientDetail"));
const LiveMonitoring = lazy(() => import("./screens/LiveMonitoring"));
const Alarms = lazy(() => import("./screens/Alarms"));
const Devices = lazy(() => import("./screens/Devices"));
const Thresholds = lazy(() => import("./screens/Thresholds"));
const Reports = lazy(() => import("./screens/Reports"));
const Team = lazy(() => import("./screens/Team"));
const Simulation = lazy(() => import("./screens/Simulation"));
const Events = lazy(() => import("./screens/Events"));

export function Navigation() {
  const { me } = useAuth();
  return (
    <nav aria-label="Main">
      <ul className="nav">
        {visibleNavItems(me?.permissions).map((item) => (
          <li key={item.to}>
            <NavLink to={item.to} className={({ isActive }) => (isActive ? "active" : undefined)}>
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function LoginNotice() {
  const { loginNotice, dismissLoginNotice } = useAuth();
  if (!loginNotice) return null;
  const revoked = loginNotice.revoked_sessions ?? 0;
  return (
    <div className="notice row spread" role="status">
      <span>
        {loginNotice.previous_login_at
          ? `Your previous sign-in was on ${formatDateTime(loginNotice.previous_login_at)}${
              loginNotice.previous_login_ip ? ` from IP address ${loginNotice.previous_login_ip}` : ""
            }. If this was not you, contact your administrator.`
          : "This is your first sign-in."}
        {revoked > 0
          ? ` ${revoked === 1 ? "One older session was" : `${revoked} older sessions were`} signed out because your account reached its limit of concurrent sessions.`
          : ""}
        {(loginNotice.failed_since_previous_login ?? 0) > 0
          ? ` There ${loginNotice.failed_since_previous_login === 1 ? "was 1 failed sign-in attempt" : `were ${loginNotice.failed_since_previous_login} failed sign-in attempts`} on your account since your previous sign-in.`
          : ""}
        {loginNotice.previous_session_unclosed
          ? " Your last session was not signed out. Always sign out on shared workstations."
          : ""}
      </span>
      <button type="button" className="secondary" onClick={dismissLoginNotice}>
        Dismiss
      </button>
    </div>
  );
}

function SessionExpiryWarning() {
  const { expiryWarning, sessionExpiresAt } = useAuth();
  if (!expiryWarning || !sessionExpiresAt) return null;
  return (
    <div className="notice" role="alert">
      Your session ends at {formatDateTime(sessionExpiresAt)}. Save your work; you will need to sign in again.
    </div>
  );
}

/** One-time message on the login page explaining why the previous session ended. */
export function SignedOutNotice() {
  const [message] = useState(() => signedOutMessage(takeSignedOutReason()));
  if (!message) return null;
  return (
    <div className="notice" role="status">
      {message}
    </div>
  );
}

/** Footer on every page, signed in or not (T751): the privacy notice is always one click away. */
export function Footer() {
  return (
    <footer className="footer muted small">
      <Link to="/privacy">Privacy notice</Link>
    </footer>
  );
}

/** /signed-out is served with Clear-Site-Data (vercel.json); it only forwards to the login page. */
export function SignedOut() {
  const [params] = useSearchParams();
  rememberSignedOutReason(params.get("reason"));
  return <Navigate to="/login" replace />;
}

function PrivacyReminder() {
  const { me } = useAuth();
  if (!me || (me.privacy_notice_required === false || (me.privacy_notice_required === undefined && me.privacy_notice_accepted_at)))
    return null;
  return (
    <div className="notice" role="status">
      Please review and accept the privacy notice on your <Link to="/profile">profile page</Link>.
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { me, signOut } = useAuth();
  return (
    <div className="shell">
      <header className="topbar">
        <Link to={homePathFor(me?.permissions)} className="brand">
          ACME Clinical
        </Link>
        <Navigation />
        <div className="user">
          <span>
            {me?.full_name} <span className="muted small">({me ? humanize(me.role) : ""})</span>
          </span>
          <button type="button" className="secondary" onClick={() => void signOut()}>
            Sign out
          </button>
          <button
            type="button"
            className="secondary"
            title="End your sessions on every device"
            onClick={() => void signOut("global")}
          >
            Sign out everywhere
          </button>
        </div>
      </header>
      <main className="content">
        <DegradedBanner />
        <SessionExpiryWarning />
        <LoginNotice />
        <PrivacyReminder />
        <Suspense fallback={<LoadingState />}>{children}</Suspense>
      </main>
      <Footer />
    </div>
  );
}

function Protected({ requires, children }: { requires?: Permission[]; children: ReactNode }) {
  return (
    <RequireAuth requires={requires}>
      <Shell>{children}</Shell>
    </RequireAuth>
  );
}

function Public({ children }: { children: ReactNode }) {
  return (
    <>
      <Suspense fallback={<LoadingState />}>{children}</Suspense>
      <Footer />
    </>
  );
}

function Home() {
  const { status, me } = useAuth();
  if (status === "loading") return <LoadingState />;
  return <Navigate to={me ? homePathFor(me.permissions) : "/login"} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <Public>
            <SignedOutNotice />
            <Login />
          </Public>
        }
      />
      <Route path="/signed-out" element={<SignedOut />} />
      <Route path="/privacy" element={<Public><PrivacyPage /></Public>} />
      <Route path="/forgot-password" element={<Public><ForgotPassword /></Public>} />
      <Route path="/reset-password" element={<Public><ResetPassword /></Public>} />
      <Route path="/" element={<Home />} />
      <Route path="/wards" element={<Protected requires={["alarm:read"]}><WardOverview /></Protected>} />
      <Route path="/patients" element={<Protected requires={["patient:read"]}><PatientList /></Protected>} />
      <Route path="/patients/:id" element={<Protected requires={["patient:read"]}><PatientDetail /></Protected>} />
      <Route path="/live" element={<Protected requires={["patient:read", "alarm:read"]}><LiveMonitoring /></Protected>} />
      <Route path="/alarms" element={<Protected requires={["alarm:read"]}><Alarms /></Protected>} />
      <Route path="/devices" element={<Protected requires={["device:read"]}><Devices /></Protected>} />
      <Route path="/thresholds" element={<Protected requires={["alarm:read"]}><Thresholds /></Protected>} />
      <Route path="/reports" element={<Protected requires={["report:read"]}><Reports /></Protected>} />
      <Route path="/team" element={<Protected requires={["staff:manage"]}><Team /></Protected>} />
      <Route path="/simulation" element={<Protected requires={["simulation:control"]}><Simulation /></Protected>} />
      <Route path="/events" element={<Protected><Events /></Protected>} />
      <Route path="/settings" element={<Protected requires={["settings:manage"]}><Settings /></Protected>} />
      <Route path="/profile" element={<Protected><Profile /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
      <StepUpDialog />
    </AuthProvider>
  );
}
