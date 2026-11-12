// Authentication screens: masking (T12/T225), generic errors and identical state (T8/T82), neutral
// recovery (T78), password change requires the current password (T3/T79), password rules (T80),
// MFA step (T1/T77), username rule (T286) and uniform staff invitations (T517/T518).
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signInWithPassword: vi.fn(),
  signOut: vi.fn(),
  resetPasswordForEmail: vi.fn(),
  updateUser: vi.fn(),
  mfa: {
    getAuthenticatorAssuranceLevel: vi.fn(),
    listFactors: vi.fn(),
    challengeAndVerify: vi.fn(),
    enroll: vi.fn(),
    unenroll: vi.fn(),
  },
}));
const apiMock = vi.hoisted(() => ({
  me: vi.fn(),
  startSession: vi.fn(),
  logout: vi.fn(),
  securitySettings: vi.fn(),
  staff: vi.fn(),
  wards: vi.fn(),
  inviteStaff: vi.fn(),
  updateStaff: vi.fn(),
  roleRequests: vi.fn(async () => []),
  requestRoleChange: vi.fn(),
  approveRoleRequest: vi.fn(),
}));
const verifyCurrentPassword = vi.hoisted(() => vi.fn());
const requestMock = vi.hoisted(() => vi.fn(async () => undefined));

vi.mock("../lib/supabase", () => ({
  getAccessToken: vi.fn(async () => null),
  supabase: { auth },
  SUPABASE_URL: "https://example.supabase.co",
}));
vi.mock("../lib/reauth", () => ({ verifyCurrentPassword }));
vi.mock("../services/api", async (orig) => {
  const real = await orig<typeof import("../services/api")>();
  return { ...real, api: apiMock, request: requestMock };
});

import { AuthContext, AuthProvider, type AuthState } from "../auth/AuthContext";
import Login from "./Login";
import ForgotPassword from "./ForgotPassword";
import ResetPassword from "./ResetPassword";
import Team from "./Team";
import { canonicalEmail, GENERIC_LOGIN_ERROR, GENERIC_RESET_MESSAGE, passwordProblems } from "../lib/authPolicy";
import { ApiError } from "../services/api";

const SESSION = { access_token: "t", user: { id: "u1", email: "nora.lindqvist@acme-clinical.org" } };

beforeEach(() => {
  vi.clearAllMocks();
  verifyCurrentPassword.mockReset();
  auth.updateUser.mockReset();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
  auth.getSession.mockResolvedValue({ data: { session: null } });
  auth.onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
  auth.signOut.mockResolvedValue({ error: null });
  auth.mfa.getAuthenticatorAssuranceLevel.mockResolvedValue({ data: { currentLevel: "aal1", nextLevel: "aal1" } });
  auth.mfa.listFactors.mockResolvedValue({ data: { all: [], totp: [] } });
  apiMock.startSession.mockResolvedValue({ previous_login_at: null, previous_login_ip: null });
  apiMock.me.mockResolvedValue({});
  apiMock.securitySettings.mockResolvedValue({ password_min_length: 12 });
});

function renderWithAuth(ui: React.ReactNode) {
  return render(
    <MemoryRouter>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  );
}

function passwordInputs(container: HTMLElement): HTMLInputElement[] {
  return [...container.querySelectorAll<HTMLInputElement>('input[autocomplete$="password"]')];
}

async function submitLogin(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  });
}

describe("password masking", () => {
  it("masks password inputs by default and reveals only on explicit toggle; blur re-masks", async () => {
    const { container } = renderWithAuth(<Login />);
    const [input] = passwordInputs(container);
    expect(input).toBeDefined();
    expect(input!.type).toBe("password");
    expect(input!.getAttribute("autocomplete")).toBe("current-password");
    expect(input!.getAttribute("spellcheck")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(input!.type).toBe("text");
    fireEvent.blur(input!);
    expect(input!.type).toBe("password");
  });

  it("change-password screen masks every field (current, new, confirm)", async () => {
    auth.getSession.mockResolvedValue({ data: { session: SESSION } });
    const { container } = renderWithAuth(<ResetPassword />);
    await screen.findByLabelText("Current password");
    const inputs = passwordInputs(container);
    expect(inputs).toHaveLength(3);
    inputs.forEach((el) => expect(el.type).toBe("password"));
  });

  // Every screen uses PasswordField; this list must stay empty.
  const PENDING_MIGRATION: string[] = [];

  it("no raw password input exists outside PasswordField", () => {
    const sources = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
    const offenders = Object.entries(sources)
      .filter(([path]) => !path.endsWith("PasswordField.tsx") && !path.endsWith(".test.tsx"))
      .filter(([path]) => !PENDING_MIGRATION.some((p) => path.endsWith(p)))
      .filter(([, src]) => /type=["']password["']/.test(src))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});

describe("login errors", () => {
  it.each(["invalid_credentials", "email_not_confirmed", "user_banned", "over_request_rate_limit"])(
    "shows the same generic message and stores nothing for %s",
    async (code) => {
      auth.signInWithPassword.mockResolvedValue({ data: { session: null }, error: { code, status: 400, message: `raw ${code}` } });
      renderWithAuth(<Login />);
      await submitLogin("Ghost@Acme-Clinical.org ", "Wrong-Pass-123");
      expect((await screen.findByRole("alert")).textContent).toMatch(GENERIC_LOGIN_ERROR);
      expect(screen.queryByText(new RegExp(code))).toBeNull();
      expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
      expect(auth.signInWithPassword).toHaveBeenCalledWith({ email: "ghost@acme-clinical.org", password: "Wrong-Pass-123" });
      expect((screen.getByLabelText("Password") as HTMLInputElement).value).toBe("");
    },
  );
});

describe("multi-factor sign-in", () => {
  it("asks for the TOTP code when the account has a verified factor", async () => {
    auth.signInWithPassword.mockResolvedValue({ data: { session: SESSION, user: SESSION.user }, error: null });
    auth.mfa.getAuthenticatorAssuranceLevel.mockResolvedValue({ data: { currentLevel: "aal1", nextLevel: "aal2" } });
    auth.mfa.listFactors.mockResolvedValue({ data: { all: [], totp: [{ id: "f1", status: "verified" }] } });
    auth.mfa.challengeAndVerify.mockResolvedValue({ error: { message: "invalid" } });
    renderWithAuth(<Login />);
    await submitLogin("admin.person@acme-clinical.org", "Violet-Harbor-82");
    const codeInput = await screen.findByLabelText("Authentication code");
    fireEvent.change(codeInput, { target: { value: "123456" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    });
    expect(auth.mfa.challengeAndVerify).toHaveBeenCalledWith({ factorId: "f1", code: "123456" });
    expect((await screen.findByRole("alert")).textContent).toMatch(/code is not valid/);
  });

  it("starts TOTP enrolment when the API requires MFA and no factor exists", async () => {
    auth.signInWithPassword.mockResolvedValue({ data: { session: SESSION, user: SESSION.user }, error: null });
    apiMock.me.mockRejectedValue(new ApiError(403, "Multi-factor authentication is required."));
    auth.mfa.enroll.mockResolvedValue({ data: { id: "f2", totp: { qr_code: "data:image/svg+xml;base64,AA", secret: "SECRET" } }, error: null });
    renderWithAuth(<Login />);
    await submitLogin("admin.person@acme-clinical.org", "Violet-Harbor-82");
    expect(await screen.findByAltText(/QR code/)).toBeTruthy();
    expect(auth.mfa.enroll).toHaveBeenCalledWith({ factorType: "totp", friendlyName: "ACME Clinical" });
  });
});

describe("password recovery", () => {
  it("shows the same neutral message whether or not the account exists", async () => {
    auth.resetPasswordForEmail
      .mockResolvedValueOnce({ data: {}, error: null })
      .mockResolvedValueOnce({ data: null, error: { status: 400, message: "User not found" } });
    for (const email of ["nora.lindqvist@acme-clinical.org", " Nobody@Acme-Clinical.org"]) {
      const view = render(
        <MemoryRouter>
          <ForgotPassword />
        </MemoryRouter>,
      );
      fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));
      });
      expect((await screen.findByRole("status")).textContent).toMatch(GENERIC_RESET_MESSAGE);
      expect(screen.queryByText(/not found/i)).toBeNull();
      view.unmount();
    }
    expect(auth.resetPasswordForEmail).toHaveBeenLastCalledWith("nobody@acme-clinical.org", expect.objectContaining({
      redirectTo: `${window.location.origin}/reset-password`,
    }));
  });
});

describe("password change", () => {
  async function fill(current: string, next: string) {
    auth.getSession.mockResolvedValue({ data: { session: SESSION } });
    renderWithAuth(<ResetPassword />);
    const currentField = await screen.findByLabelText("Current password");
    await waitFor(() => expect(apiMock.securitySettings).toHaveBeenCalled());
    await act(async () => undefined); // let the configured policy load
    fireEvent.change(currentField, { target: { value: current } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: next } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    });
  }

  it("rejects a wrong current password without updating", async () => {
    verifyCurrentPassword.mockResolvedValue(false);
    await fill("Wrong-Current-1", "Violet-Harbor-Lantern-82");
    expect((await screen.findByRole("alert")).textContent).toMatch("The current password is incorrect.");
    expect(auth.updateUser).not.toHaveBeenCalled();
  });

  it("requires the current password", async () => {
    await fill("", "Violet-Harbor-Lantern-82");
    expect((await screen.findByRole("alert")).textContent).toMatch("Enter your current password.");
    expect(verifyCurrentPassword).not.toHaveBeenCalled();
    expect(auth.updateUser).not.toHaveBeenCalled();
  });

  it("rejects a weak new password before contacting Supabase", async () => {
    await fill("Old-Password-77x", "password1234");
    expect((await screen.findByRole("alert")).textContent).toMatch(/upper-case/);
    expect(auth.updateUser).not.toHaveBeenCalled();
  });

  it("honours the administrator-configured minimum length", async () => {
    apiMock.securitySettings.mockResolvedValue({ password_min_length: 20 });
    await fill("Old-Password-77x", "Violet-Harbor-82");
    await waitFor(() => expect((screen.getByRole("alert")).textContent).toMatch("Use 20 to 128 characters."));
    expect(auth.updateUser).not.toHaveBeenCalled();
  });

  it("updates only after the current password verifies, then signs out everywhere", async () => {
    verifyCurrentPassword.mockResolvedValue(true);
    auth.updateUser.mockResolvedValue({ data: {}, error: null });
    await fill("Old-Password-77x", "Violet-Harbor-Lantern-82");
    expect(verifyCurrentPassword).toHaveBeenCalledWith("nora.lindqvist@acme-clinical.org", "Old-Password-77x");
    expect(auth.updateUser).toHaveBeenCalledWith({ password: "Violet-Harbor-Lantern-82", current_password: "Old-Password-77x" });
    expect(requestMock).toHaveBeenCalledWith("POST", "/v1/auth/logout", expect.objectContaining({ body: { scope: "global" } }));
  });
});

describe("auth policy helpers", () => {
  it("applies the same username rule as the API", () => {
    expect(canonicalEmail("  Joe@ACME-Clinical.org ")).toBe("joe@acme-clinical.org");
  });

  it.each(["Short1a", "alllowercase1234x", "NoDigitsHereAtAll", "AcmeClinical2026x", "Password123456!", "Abcdefgh12345"])(
    "rejects %s",
    (pw) => expect(passwordProblems(pw)).not.toEqual([]),
  );

  it("accepts a strong passphrase and rejects context words", () => {
    expect(passwordProblems("Violet-Harbor-Lantern-82")).toEqual([]);
    expect(passwordProblems("Lindqvist-Harbor-82", 12, ["lindqvist"])).not.toEqual([]);
  });
});

describe("team invitations", () => {
  it("shows the same outcome message for every invitation and never asks for a password", async () => {
    apiMock.staff.mockResolvedValue([]);
    apiMock.wards.mockResolvedValue([]);
    apiMock.inviteStaff.mockResolvedValue({ detail: "ok" });
    const value = { me: { user_id: "admin" } } as unknown as AuthState;
    const { container } = render(
      <AuthContext.Provider value={value}>
        <MemoryRouter>
          <Team />
        </MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(passwordInputs(container)).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Work email"), { target: { value: " New.Person@Acme-Clinical.org " } });
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "New Person" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    });
    expect(await screen.findByText(/If the address can receive invitations/)).toBeTruthy();
    expect(apiMock.inviteStaff).toHaveBeenCalledWith(expect.objectContaining({ email: "new.person@acme-clinical.org" }));
  });
});
