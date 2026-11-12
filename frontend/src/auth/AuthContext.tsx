// Auth state: Supabase session + the server-side profile from GET /v1/me (role and permissions are
// authoritative on the server; the UI only uses them to shape navigation).
// Session controls (docs/security/sessions.md): every Supabase session is registered with the API before
// any other API call; real user input sends a throttled heartbeat; the idle timeout (session_idle_minutes)
// and the absolute expiry sign the user out; any 401 runs the full logout clean-up.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase";
import { api, errorMessage, setUnauthorizedHandler } from "../services/api";
import type { Me, Permission } from "../services/types";
import { useIdleTimeout, useSessionExpiry } from "../hooks/useIdleTimeout";
import { onSignOutElsewhere, performLogout, registerSession, type LogoutScope, type SessionInfo } from "./session";

export interface AuthState {
  status: "loading" | "signed_out" | "signed_in";
  session: Session | null;
  me: Me | null;
  error: string | null;
  loginNotice: SessionInfo | null;
  signIn: (email: string, password: string) => Promise<void>;
  /** "global" also ends the user's sessions on every other device. */
  signOut: (scope?: LogoutScope) => Promise<void>;
  refreshMe: () => Promise<void>;
  dismissLoginNotice: () => void;
  can: (perm: Permission) => boolean;
  /** Absolute session expiry (ISO time) and whether the "ending soon" warning is due. */
  sessionExpiresAt?: string | null;
  expiryWarning?: boolean;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>.");
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [error, setError] = useState<string | null>(null);
  const [loginNotice, setLoginNotice] = useState<SessionInfo | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [expiryWarning, setExpiryWarning] = useState(false);
  const loadedFor = useRef<string | null>(null);
  // One registration per Supabase session, shared by signIn and the session effect.
  const registration = useRef<{ uid: string; promise: Promise<SessionInfo> } | null>(null);

  const ensureRegistered = useCallback((uid: string): Promise<SessionInfo> => {
    if (registration.current?.uid !== uid) {
      const promise = registerSession();
      registration.current = { uid, promise };
      promise.then((info) => setExpiresAt(info.expires_at ?? null)).catch(() => undefined);
    }
    return registration.current.promise;
  }, []);

  const resetState = useCallback(() => {
    loadedFor.current = null;
    registration.current = null;
    setMe(null);
    setLoginNotice(null);
    setExpiresAt(null);
    setExpiryWarning(false);
    setStatus("signed_out");
  }, []);

  const signOut = useCallback(
    async (scope: LogoutScope = "local") => {
      await performLogout({ reason: "user", scope });
      resetState();
    },
    [resetState],
  );

  // Any 401 from the API (revoked, idle, expired, unknown session) => full clean-up, not just signOut().
  useEffect(() => {
    setUnauthorizedHandler(async () => {
      await performLogout({ reason: "revoked", notifyServer: false });
      resetState();
    });
    const stop = onSignOutElsewhere(() => {
      if (loadedFor.current === null) return; // this tab is not signed in
      void performLogout({ reason: "user", notifyServer: false, announce: false }).then(resetState);
    });
    return () => {
      setUnauthorizedHandler(null);
      stop();
    };
  }, [resetState]);

  const loadMe = useCallback(async () => {
    try {
      const profile = await api.me();
      setMe(profile);
      setError(null);
      setStatus("signed_in");
    } catch (err) {
      setMe(null);
      setError(errorMessage(err));
      setStatus("signed_out");
    }
  }, []);

  useEffect(() => {
    let active = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      if (!data.session) setStatus("signed_out");
    });
    const { data: sub } = supabase.auth.onAuthStateChange((event, next) => {
      setSession(next);
      if (event === "SIGNED_OUT" || !next) resetState();
    });
    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, [resetState]);

  // Register the session (sign-in or reload), then load the profile, whenever a different user is signed in.
  useEffect(() => {
    const uid = session?.user.id ?? null;
    if (uid && loadedFor.current !== uid) {
      loadedFor.current = uid;
      setStatus("loading");
      void ensureRegistered(uid)
        .then(() => loadMe())
        .catch((err: unknown) => {
          setError(errorMessage(err));
          setStatus("signed_out");
        });
    }
  }, [session, loadMe, ensureRegistered]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      loadedFor.current = null; // force a fresh registration + GET /v1/me for this sign-in
      registration.current = null;
      const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password });
      if (authError || !data.user) {
        // Generic message: do not reveal whether the account exists or is locked.
        throw new Error("Invalid email or password.");
      }
      try {
        const info = await ensureRegistered(data.user.id);
        setLoginNotice(info.new_session === false ? null : info);
      } catch {
        setLoginNotice(null);
      }
    },
    [ensureRegistered],
  );

  const signedIn = status === "signed_in" && !!me;
  const heartbeat = useCallback(() => {
    void registerSession()
      .then((info) => setExpiresAt(info.expires_at ?? null))
      .catch(() => undefined); // a 401 already triggered the logout handler
  }, []);
  const onIdle = useCallback(() => {
    void performLogout({ reason: "idle" }).then(resetState);
  }, [resetState]);
  useIdleTimeout({
    idleMs: Math.max(1, me?.session_idle_minutes ?? 15) * 60_000,
    onIdle,
    onActivity: heartbeat,
    enabled: signedIn,
  });
  useSessionExpiry(
    signedIn ? expiresAt : null,
    () => setExpiryWarning(true),
    () => void performLogout({ reason: "expired" }).then(resetState),
  );

  const can = useCallback((perm: Permission) => !!me?.permissions.includes(perm), [me]);

  const value = useMemo<AuthState>(
    () => ({
      status,
      session,
      me,
      error,
      loginNotice,
      signIn,
      signOut,
      refreshMe: loadMe,
      dismissLoginNotice: () => setLoginNotice(null),
      can,
      sessionExpiresAt: expiresAt,
      expiryWarning,
    }),
    [status, session, me, error, loginNotice, signIn, signOut, loadMe, can, expiresAt, expiryWarning],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
