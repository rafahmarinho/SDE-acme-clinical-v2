// Client-side idle timeout. Only real user input counts as activity: Realtime messages, polling and
// automatic token refreshes never reset the timer. `onActivity` (the server heartbeat that keeps the
// server-side idle window open) is throttled. The server enforces the same window independently.
import { useEffect, useRef } from "react";

export const ACTIVITY_EVENTS = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
export const HEARTBEAT_INTERVAL_MS = 60_000;

interface Options {
  idleMs: number;
  onIdle: () => void;
  onActivity?: () => void;
  enabled?: boolean;
  heartbeatMs?: number;
}

export function useIdleTimeout({ idleMs, onIdle, onActivity, enabled = true, heartbeatMs = HEARTBEAT_INTERVAL_MS }: Options): void {
  const onIdleRef = useRef(onIdle);
  const onActivityRef = useRef(onActivity);
  onIdleRef.current = onIdle;
  onActivityRef.current = onActivity;

  useEffect(() => {
    if (!enabled || !(idleMs > 0)) return;
    let timer = window.setTimeout(() => onIdleRef.current(), idleMs);
    let lastBeat = Date.now();
    const activity = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => onIdleRef.current(), idleMs);
      if (Date.now() - lastBeat >= heartbeatMs) {
        lastBeat = Date.now();
        onActivityRef.current?.();
      }
    };
    for (const e of ACTIVITY_EVENTS) window.addEventListener(e, activity, { passive: true });
    return () => {
      window.clearTimeout(timer);
      for (const e of ACTIVITY_EVENTS) window.removeEventListener(e, activity);
    };
  }, [idleMs, enabled, heartbeatMs]);
}

/** Schedules a warning shortly before the absolute session expiry and the expiry itself. */
export function useSessionExpiry(expiresAt: string | null | undefined, onWarn: () => void, onExpire: () => void,
  warnBeforeMs = 10 * 60_000): void {
  const warnRef = useRef(onWarn);
  const expireRef = useRef(onExpire);
  warnRef.current = onWarn;
  expireRef.current = onExpire;

  useEffect(() => {
    const at = expiresAt ? Date.parse(expiresAt) : NaN;
    if (Number.isNaN(at)) return;
    const left = at - Date.now();
    const warn = window.setTimeout(() => warnRef.current(), Math.max(0, left - warnBeforeMs));
    const expire = window.setTimeout(() => expireRef.current(), Math.max(0, left));
    return () => {
      window.clearTimeout(warn);
      window.clearTimeout(expire);
    };
  }, [expiresAt, warnBeforeMs]);
}
