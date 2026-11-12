// Post-login destination guard (T11/T125): only same-origin, in-app absolute paths are followed.
// Anything else (external URLs, protocol-relative "//host", backslash tricks, javascript:, auth pages)
// falls back to the caller's default.
const AUTH_PAGES = ["/login", "/signed-out", "/forgot-password", "/reset-password"];

export function safeNext(raw: unknown, fallback: string): string {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > 512) return fallback;
  if (!raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || /[\u0000-\u001f\u007f]/.test(raw)) return fallback;
  let url: URL;
  try {
    url = new URL(raw, "https://app.invalid");
  } catch {
    return fallback;
  }
  if (url.origin !== "https://app.invalid") return fallback;
  if (AUTH_PAGES.some((p) => url.pathname === p || url.pathname.startsWith(`${p}/`))) return fallback;
  return `${url.pathname}${url.search}${url.hash}`;
}
