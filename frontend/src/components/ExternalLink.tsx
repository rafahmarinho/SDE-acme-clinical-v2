import type { AnchorHTMLAttributes } from "react";

// Reverse-tabnabbing protection (T512/T513). Every new tab or window opened by the SPA goes
// through these helpers so the opened page never gets a `window.opener` reference or a Referer
// carrying in-app paths (patient ids). Cross-Origin-Opener-Policy: same-origin (vercel.json)
// adds browser-level isolation on top.

const OPENER_FEATURES = "noopener,noreferrer";

/** Returns the URL if it is HTTPS (or same-origin); otherwise null. Blocks javascript:, data:, http:. */
export function safeExternalUrl(raw: string, base: string = window.location.origin): URL | null {
  let url: URL;
  try {
    url = new URL(raw, base);
  } catch {
    return null;
  }
  if (url.origin === window.location.origin) return url;
  return url.protocol === "https:" ? url : null;
}

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "target" | "rel" | "href"> & { href: string };

/** Link that opens in a new tab without opener access. Non-HTTPS URLs are rendered as plain text. */
export function ExternalLink({ href, children, ...rest }: Props) {
  const url = safeExternalUrl(href);
  if (!url) return <span>{children}</span>;
  return (
    <a {...rest} href={url.toString()} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
      {children}
    </a>
  );
}

/**
 * Opens a URL (e.g. a short-lived Supabase Storage signed URL) in a new tab with noopener/noreferrer.
 * `allowedOrigin` restricts the destination to one exact origin.
 */
export function openSafely(raw: string, allowedOrigin?: string): void {
  const url = safeExternalUrl(raw);
  if (!url) throw new Error("Blocked a non-HTTPS URL.");
  if (allowedOrigin !== undefined && url.origin !== new URL(allowedOrigin).origin) {
    throw new Error("Blocked an unexpected destination.");
  }
  const win = window.open(url.toString(), "_blank", OPENER_FEATURES);
  if (win) win.opener = null; // belt and braces for engines that ignore noopener
}
