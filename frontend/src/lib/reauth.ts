// Re-verify the current password before a password change (T3) WITHOUT replacing the signed-in session
// (which would drop an administrator's MFA level). A throw-away, non-persistent Supabase client signs
// in, and that extra session is revoked immediately. Failures are throttled by Supabase Auth rate
// limits and count towards the per-account lockout hook.
import { createClient } from "@supabase/supabase-js";
import { SUPABASE_URL } from "./supabase";

export async function verifyCurrentPassword(email: string, password: string): Promise<boolean> {
  const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
  if (typeof anonKey !== "string" || !anonKey) return false;
  const memory = new Map<string, string>();
  const verifier = createClient(SUPABASE_URL, anonKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
      storageKey: "acme-reauth",
      storage: {
        getItem: (k) => memory.get(k) ?? null,
        setItem: (k, v) => void memory.set(k, v),
        removeItem: (k) => void memory.delete(k),
      },
    },
  });
  const { data, error } = await verifier.auth.signInWithPassword({ email, password });
  if (error || !data.session) return false;
  await verifier.auth.signOut({ scope: "local" }); // revoke the verification session at once
  return true;
}
