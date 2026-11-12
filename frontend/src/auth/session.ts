// Session lifecycle helpers: server-side registration/heartbeat, logout that revokes the session on the
// server and wipes the browser, and cross-tab sign-out. See docs/security/sessions.md.
import { supabase } from "../lib/supabase";
import { request } from "../services/api";
import type { SessionStart } from "../services/types";

/** Response of POST /v1/auth/session (registration on sign-in, then the activity heartbeat). */
export interface SessionInfo extends SessionStart {
  session_id?: string;
  new_session?: boolean;
  revoked_sessions?: number;
  previous_session_unclosed?: boolean;
  expires_at?: string | null;
}

export type LogoutReason = "user" | "idle" | "expired" | "revoked";
export type LogoutScope = "local" | "global";

const SIGNED_OUT_KEY = "acme.signedOutReason";
const CHANNEL_NAME = "acme-session";

/** Register the current Supabase session with the API, or record user activity for an existing one. */
export function registerSession(): Promise<SessionInfo> {
  return request<SessionInfo>("POST", "/v1/auth/session");
}

/** Remove everything this origin keeps in the browser (Web Storage, IndexedDB, Cache Storage, cookies). */
export async function clearBrowserData(): Promise<void> {
  try {
    window.sessionStorage.clear();
  } catch {
    /* storage unavailable */
  }
  try {
    window.localStorage.clear();
  } catch {
    /* storage unavailable */
  }
  try {
    const dbs = typeof indexedDB !== "undefined" && indexedDB.databases ? await indexedDB.databases() : [];
    for (const db of dbs) if (db.name) indexedDB.deleteDatabase(db.name);
  } catch {
    /* not supported */
  }
  try {
    if (typeof caches !== "undefined") for (const key of await caches.keys()) await caches.delete(key);
  } catch {
    /* not supported */
  }
  // The app sets no cookies; expire any script-visible cookie defensively.
  for (const part of document.cookie.split(";")) {
    const name = part.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; Max-Age=0; path=/`;
  }
}

/** Reason shown once on the login page after a full-page navigation (then forgotten). */
export function takeSignedOutReason(): LogoutReason | null {
  try {
    const value = window.sessionStorage.getItem(SIGNED_OUT_KEY) as LogoutReason | null;
    window.sessionStorage.removeItem(SIGNED_OUT_KEY);
    return value;
  } catch {
    return null;
  }
}

function broadcast(): BroadcastChannel | null {
  return typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(CHANNEL_NAME) : null;
}

/** Sign out every other tab of this origin when one tab signs out (shared ward workstations). */
export function onSignOutElsewhere(handler: () => void): () => void {
  const channel = broadcast();
  if (!channel) return () => undefined;
  channel.onmessage = (event: MessageEvent) => {
    if (event.data === "signed-out") handler();
  };
  return () => channel.close();
}

let inProgress: Promise<void> | null = null;

export interface LogoutOptions {
  reason: LogoutReason;
  scope?: LogoutScope;
  /** false when the server already ended the session (401) or another tab signed out. */
  notifyServer?: boolean;
  /** Full-page navigation so no patient data survives in memory; injectable for tests. */
  navigate?: (url: string) => void;
  /** false when triggered by another tab's broadcast, to avoid echoing it. */
  announce?: boolean;
}

/**
 * Logout: revoke the session server-side (refresh token deleted, Clear-Site-Data), stop Realtime, drop the
 * tokens, wipe browser storage and leave with location.replace so Back cannot show cached screens.
 * Every step runs even if an earlier one fails; concurrent calls share one run.
 */
export function performLogout(opts: LogoutOptions): Promise<void> {
  if (inProgress) return inProgress;
  const { reason, scope = "local", notifyServer = true, announce = true } = opts;
  const navigate = opts.navigate ?? ((url: string) => window.location.replace(url));
  inProgress = (async () => {
    try {
      if (notifyServer) {
        await request<void>("POST", "/v1/auth/logout", {
          body: scope === "global" ? { scope } : undefined,
          timeoutMs: 5000,
        });
      }
    } catch {
      // the local clean-up below must happen even if the API is unreachable
    }
    try {
      await supabase.removeAllChannels();
    } catch {
      /* ignore */
    }
    try {
      await supabase.auth.signOut({ scope: "local" }); // server already revoked it (or every session for "global")
    } catch {
      /* ignore */
    }
    await clearBrowserData();
    try {
      window.sessionStorage.setItem(SIGNED_OUT_KEY, reason);
    } catch {
      /* ignore */
    }
    if (announce) {
      const channel = broadcast();
      channel?.postMessage("signed-out");
      channel?.close();
    }
    // /signed-out is served with Clear-Site-Data (vercel.json) and then forwards to /login. The reason is
    // carried in the URL because Clear-Site-Data also wipes sessionStorage; it is an allow-listed word only.
    navigate(signedOutPath(reason));
  })().finally(() => {
    inProgress = null;
  });
  return inProgress;
}

const REASONS: readonly LogoutReason[] = ["user", "idle", "expired", "revoked"];

export function signedOutPath(reason: LogoutReason): string {
  return `/signed-out?reason=${encodeURIComponent(reason)}`;
}

/** Re-store the (allow-listed) reason after the /signed-out page load cleared the browser storage. */
export function rememberSignedOutReason(raw: string | null): void {
  const reason = REASONS.find((r) => r === raw);
  if (!reason) return;
  try {
    window.sessionStorage.setItem(SIGNED_OUT_KEY, reason);
  } catch {
    /* ignore */
  }
}

export function signedOutMessage(reason: LogoutReason | null): string | null {
  switch (reason) {
    case "idle":
      return "You were signed out after a period of inactivity.";
    case "expired":
      return "Your session reached its maximum duration. Please sign in again.";
    case "revoked":
      return "Your session was ended (for example because your account signed in on another device).";
    case "user":
      return "You have been signed out.";
    default:
      return null;
  }
}
