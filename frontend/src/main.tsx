import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

/**
 * Defence in depth against clickjacking (T119). The primary controls are the
 * `frame-ancestors 'none'` CSP directive and `X-Frame-Options: DENY` sent by Vercel
 * (frontend/vercel.json); this check only keeps the UI from rendering if both are bypassed.
 */
function isFramed(win: Window = window): boolean {
  try {
    return win.self !== win.top;
  } catch {
    return true; // cross-origin parent: accessing top threw
  }
}

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root not found.");

if (isFramed()) {
  root.textContent = "ACME Clinical cannot be displayed inside a frame. Open it directly in your browser.";
} else {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
