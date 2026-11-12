// Privacy controls on the profile screen (T238/T239/T240/T741/T751/T752).
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../lib/supabase", () => ({
  getAccessToken: vi.fn(async () => "token"),
  supabase: { auth: { updateUser: vi.fn(async () => ({ error: null })) } },
  SUPABASE_URL: "https://example.supabase.co",
}));

const requestMock = vi.fn();
vi.mock("../services/api", async (orig) => {
  const actual = await orig<typeof import("../services/api")>();
  return { ...actual, request: (...args: unknown[]) => requestMock(...args) };
});

import { AuthContext, type AuthState } from "../auth/AuthContext";
import Profile, { PRIVACY_NOTICE_VERSION, PrivacyNotice } from "./Profile";
import type { Me } from "../services/types";

function renderProfile(overrides: Record<string, unknown> = {}) {
  const me = {
    user_id: "00000000-0000-4000-8000-000000000001",
    email: "nurse@acme.test",
    full_name: "Test Nurse",
    role: "nurse",
    ward_ids: [],
    permissions: ["patient:read"],
    previous_login_at: null,
    privacy_notice_accepted_at: null,
    session_idle_minutes: 15,
    privacy_notice_version: null,
    privacy_notice_required: true,
    erasure_requested_at: null,
    ...overrides,
  } as unknown as Me;
  const auth: AuthState = {
    status: "signed_in",
    session: null,
    me,
    error: null,
    loginNotice: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
    refreshMe: vi.fn(async () => undefined),
    dismissLoginNotice: vi.fn(),
    can: () => false,
  };
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

beforeEach(() => requestMock.mockReset());

describe("privacy notice", () => {
  it("lists purposes, categories, recipients, retention and rights", () => {
    render(<PrivacyNotice />);
    for (const h of [/purposes/i, /categories/i, /recipients/i, /retention/i, /your rights/i]) {
      expect(screen.getByRole("heading", { name: h })).toBeTruthy();
    }
    expect(screen.getByText(new RegExp(`Version ${PRIVACY_NOTICE_VERSION}`))).toBeTruthy();
  });

  it("requires an explicit acknowledgement (unchecked by default) before profile edits", () => {
    renderProfile();
    const box = screen.getByRole("checkbox", { name: /read and understood/i }) as HTMLInputElement;
    expect(box.checked).toBe(false);
    const accept = screen.getByRole("button", { name: /acknowledge privacy notice/i }) as HTMLButtonElement;
    expect(accept.disabled).toBe(true);
    expect((screen.getByLabelText(/full name/i) as HTMLInputElement).closest("fieldset")?.disabled).toBe(true);
    fireEvent.click(box);
    expect(accept.disabled).toBe(false);
  });

  it("sends the current notice version when acknowledged", async () => {
    requestMock.mockResolvedValue(undefined);
    renderProfile();
    fireEvent.click(screen.getByRole("checkbox", { name: /read and understood/i }));
    fireEvent.click(screen.getByRole("button", { name: /acknowledge privacy notice/i }));
    await vi.waitFor(() =>
      expect(requestMock).toHaveBeenCalledWith("POST", "/v1/me/privacy-notice", {
        body: { notice_version: PRIVACY_NOTICE_VERSION },
      }),
    );
  });

  it("re-prompts when an older version was accepted", () => {
    renderProfile({ privacy_notice_version: "2020-01-01", privacy_notice_required: true, privacy_notice_accepted_at: "2020-01-01T00:00:00Z" });
    expect(screen.getByRole("checkbox", { name: /read and understood/i })).toBeTruthy();
  });
});

describe("personal data controls", () => {
  it("shows every personal field and allows editing once the notice is acknowledged", () => {
    renderProfile({ privacy_notice_required: false, privacy_notice_version: PRIVACY_NOTICE_VERSION });
    expect(screen.getByText("nurse@acme.test")).toBeTruthy();
    const name = screen.getByLabelText(/full name/i) as HTMLInputElement;
    expect(name.value).toBe("Test Nurse");
    expect(name.closest("fieldset")?.disabled).toBe(false);
    expect(screen.getByLabelText(/new work e-mail/i)).toBeTruthy();
  });

  it("offers a re-authenticated export of my data", async () => {
    requestMock.mockResolvedValue({ format: "acme-clinical-personal-data/v1" });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    renderProfile({ privacy_notice_required: false });
    const button = screen.getByRole("button", { name: /export my data/i }) as HTMLButtonElement;
    expect(button.disabled).toBe(true); // password required first
    fireEvent.change(screen.getAllByLabelText(/^current password$/i)[0]!, { target: { value: "pw" } });
    fireEvent.click(button);
    await vi.waitFor(() =>
      expect(requestMock).toHaveBeenCalledWith("POST", "/v1/me/export", { body: { reauthentication: "pw" } }),
    );
  });

  it("offers account deletion that needs the password and a typed confirmation", () => {
    renderProfile({ privacy_notice_required: false });
    const button = screen.getByRole("button", { name: /request account deletion/i }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getAllByLabelText(/^current password$/i)[1]!, { target: { value: "pw" } });
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/type delete my account/i), { target: { value: "DELETE MY ACCOUNT" } });
    expect(button.disabled).toBe(false);
  });

  it("shows a pending erasure request instead of the form", () => {
    renderProfile({ privacy_notice_required: false, erasure_requested_at: "2026-11-01T10:00:00Z" });
    expect(screen.queryByRole("button", { name: /request account deletion/i })).toBeNull();
    expect(screen.getByText(/erasure requested on/i)).toBeTruthy();
  });
});
