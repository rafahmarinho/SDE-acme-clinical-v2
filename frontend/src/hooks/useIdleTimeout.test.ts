import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useIdleTimeout, useSessionExpiry } from "./useIdleTimeout";

const IDLE = 15 * 60_000;

describe("useIdleTimeout (T24/T90)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("signs out after the idle period without user input", () => {
    const onIdle = vi.fn();
    renderHook(() => useIdleTimeout({ idleMs: IDLE, onIdle }));
    vi.advanceTimersByTime(IDLE - 1);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onIdle).toHaveBeenCalledOnce();
  });

  it("real user input resets the timer", () => {
    const onIdle = vi.fn();
    renderHook(() => useIdleTimeout({ idleMs: IDLE, onIdle }));
    vi.advanceTimersByTime(IDLE - 1000);
    window.dispatchEvent(new Event("keydown"));
    vi.advanceTimersByTime(IDLE - 1000);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(onIdle).toHaveBeenCalledOnce();
  });

  it("realtime updates, polling and background events do not count as activity", () => {
    const onIdle = vi.fn();
    renderHook(() => useIdleTimeout({ idleMs: IDLE, onIdle }));
    for (let i = 0; i < 14; i++) {
      vi.advanceTimersByTime(60_000);
      window.dispatchEvent(new MessageEvent("message", { data: { table: "readings" } }));
      window.dispatchEvent(new Event("online"));
      window.dispatchEvent(new Event("scroll"));
    }
    vi.advanceTimersByTime(60_000);
    expect(onIdle).toHaveBeenCalledOnce();
  });

  it("sends the server heartbeat at most once per interval", () => {
    const onActivity = vi.fn();
    renderHook(() => useIdleTimeout({ idleMs: IDLE, onIdle: vi.fn(), onActivity, heartbeatMs: 60_000 }));
    for (let i = 0; i < 10; i++) {
      window.dispatchEvent(new Event("pointerdown"));
      vi.advanceTimersByTime(10_000);
    }
    expect(onActivity).toHaveBeenCalledTimes(1);
  });

  it("does nothing while signed out", () => {
    const onIdle = vi.fn();
    renderHook(() => useIdleTimeout({ idleMs: IDLE, onIdle, enabled: false }));
    vi.advanceTimersByTime(IDLE * 2);
    expect(onIdle).not.toHaveBeenCalled();
  });
});

describe("useSessionExpiry (T25/T92)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("warns 10 minutes before the absolute expiry and expires on time", () => {
    const onWarn = vi.fn();
    const onExpire = vi.fn();
    const expiresAt = new Date(Date.now() + 60 * 60_000).toISOString();
    renderHook(() => useSessionExpiry(expiresAt, onWarn, onExpire));
    vi.advanceTimersByTime(50 * 60_000);
    expect(onWarn).toHaveBeenCalledOnce();
    expect(onExpire).not.toHaveBeenCalled();
    vi.advanceTimersByTime(10 * 60_000);
    expect(onExpire).toHaveBeenCalledOnce();
  });
});
