// Read-only Supabase Realtime subscription (postgres_changes) with automatic polling fallback.
// RLS on readings/alarms/monitors decides which rows this user receives; payloads are treated as
// change signals and the screen re-fetches through the API (authoritative, permission-checked).
import { useEffect, useRef, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase";

export type RealtimeTable = "readings" | "alarms" | "monitors";
export type ConnectionState = "connecting" | "live" | "polling" | "offline";

export interface RealtimeChange {
  table: RealtimeTable;
  eventType: "INSERT" | "UPDATE" | "DELETE";
  record: Record<string, unknown>;
}

interface Options {
  tables: RealtimeTable[];
  onChange: (change: RealtimeChange) => void;
  /** Called every `pollMs` while the realtime channel is not connected. */
  poll: () => void | Promise<void>;
  pollMs?: number;
  enabled?: boolean;
}

let channelSeq = 0;

export function useRealtime({ tables, onChange, poll, pollMs = 5000, enabled = true }: Options): ConnectionState {
  const [state, setState] = useState<ConnectionState>("connecting");
  const onChangeRef = useRef(onChange);
  const pollRef = useRef(poll);
  onChangeRef.current = onChange;
  pollRef.current = poll;
  const key = tables.slice().sort().join(",");

  useEffect(() => {
    if (!enabled) return;
    let channel: RealtimeChannel | null = null;
    let disposed = false;
    setState("connecting");

    channel = supabase.channel(`acme-${key}-${++channelSeq}`);
    for (const table of key.split(",") as RealtimeTable[]) {
      channel.on("postgres_changes", { event: "*", schema: "public", table }, (payload) => {
        const record = (payload.eventType === "DELETE" ? payload.old : payload.new) as Record<string, unknown>;
        onChangeRef.current({ table, eventType: payload.eventType, record: record ?? {} });
      });
    }
    channel.subscribe((status) => {
      if (disposed) return;
      if (status === "SUBSCRIBED") setState("live");
      else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") setState("polling");
      else if (status === "CLOSED") setState(navigator.onLine ? "polling" : "offline");
    });

    // If the channel has not connected within 8 s, fall back to polling.
    const fallback = window.setTimeout(() => {
      setState((s) => (s === "connecting" ? "polling" : s));
    }, 8000);

    return () => {
      disposed = true;
      window.clearTimeout(fallback);
      if (channel) void supabase.removeChannel(channel);
    };
  }, [key, enabled]);

  useEffect(() => {
    if (!enabled || state === "live") return;
    const t = window.setInterval(() => {
      if (document.visibilityState === "visible") void pollRef.current();
    }, pollMs);
    return () => window.clearInterval(t);
  }, [state, pollMs, enabled]);

  useEffect(() => {
    const offline = () => setState("offline");
    const online = () => setState((s) => (s === "offline" ? "polling" : s));
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
    };
  }, []);

  return state;
}

export function ConnectionLabel(state: ConnectionState): string {
  switch (state) {
    case "live":
      return "Live (realtime)";
    case "polling":
      return "Realtime unavailable — refreshing every 5 s";
    case "offline":
      return "Offline — data may be out of date";
    default:
      return "Connecting…";
  }
}
