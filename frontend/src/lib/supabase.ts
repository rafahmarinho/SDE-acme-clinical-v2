// Supabase browser client: public anon key only (RLS enforces access). Used for Auth (email/password,
// recovery), and read-only Realtime/reference reads. All writes go through the ACME Clinical API.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

function requireEnv(name: "VITE_SUPABASE_URL" | "VITE_SUPABASE_ANON_KEY"): string {
  const value = import.meta.env[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required environment variable ${name}.`);
  }
  return value.trim();
}

export const SUPABASE_URL = requireEnv("VITE_SUPABASE_URL").replace(/\/+$/, "");
const SUPABASE_ANON_KEY = requireEnv("VITE_SUPABASE_ANON_KEY");

if (!import.meta.env.DEV && !SUPABASE_URL.startsWith("https://")) {
  throw new Error("VITE_SUPABASE_URL must use https.");
}

// Session storage policy (docs/security/sessions.md):
// * sessionStorage, never localStorage or cookies: the session survives a reload (PRD) but ends when the
//   tab/browser is closed, so the next person at a shared ward workstation is never signed in as the
//   previous clinician. There is deliberately no "remember me" option.
// * PKCE: recovery/confirmation links carry a one-time `code`, never tokens; supabase-js exchanges it once
//   and strips it from the address bar (history.replaceState). Tokens are never put in URLs.
// * Supabase rotates the refresh token on every refresh and issues a new random session_id per sign-in.
function sessionStore(): Storage | undefined {
  return typeof window !== "undefined" ? window.sessionStorage : undefined;
}

export const supabase: SupabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: sessionStore(),
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true, // password-recovery links land on /reset-password with a PKCE code
    flowType: "pkce",
  },
  realtime: {
    params: { eventsPerSecond: 10 },
  },
});

/** Current access token, or null when signed out. */
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
