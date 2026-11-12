/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const ROOT = fileURLToPath(new URL(".", import.meta.url));

interface VercelHeaderRule {
  source: string;
  headers: { key: string; value: string }[];
}

/** Response headers that the Vercel deployment sends on every route (see vercel.json). */
function vercelHeaders(): Record<string, string> {
  const cfg = JSON.parse(readFileSync(new URL("./vercel.json", import.meta.url), "utf8")) as { headers: VercelHeaderRule[] };
  const all = cfg.headers.find((rule) => rule.source === "/(.*)");
  if (!all) throw new Error("vercel.json must define a header rule for /(.*)");
  return Object.fromEntries(all.headers.map((h) => [h.key, h.value]));
}

/**
 * Build-time guard for the deployment-specific CSP (T331/T1469/T322).
 *
 * vercel.json cannot interpolate environment variables, so the API and Supabase origins in the
 * Content-Security-Policy are edited per deployment (docs/security/web-frontend.md). When the VITE_
 * variables are present (always on Vercel) the build fails if they are not HTTPS or if the CSP
 * connect-src does not list exactly those origins (https + wss for Supabase Realtime).
 */
function cspDeploymentGuard(): Plugin {
  return {
    name: "acme-csp-deployment-guard",
    apply: "build",
    configResolved(config) {
      const env = loadEnv(config.mode, ROOT, "VITE_");
      const configured = [env.VITE_SUPABASE_URL, env.VITE_API_BASE_URL].filter((v): v is string => !!v);
      if (configured.length === 0) {
        config.logger.warn("[csp] VITE_SUPABASE_URL / VITE_API_BASE_URL not set: skipping CSP origin check.");
        return;
      }
      const csp = vercelHeaders()["Content-Security-Policy"] ?? "";
      const connect = (csp.split(";").map((d) => d.trim()).find((d) => d.startsWith("connect-src ")) ?? "").split(/\s+/);
      const required: string[] = [];
      for (const value of configured) {
        const url = new URL(value);
        if (url.protocol !== "https:") throw new Error(`[csp] ${value} must use https://`);
        required.push(url.origin);
      }
      if (env.VITE_SUPABASE_URL) required.push(new URL(env.VITE_SUPABASE_URL).origin.replace(/^https:/, "wss:"));
      const missing = required.filter((origin) => !connect.includes(origin));
      if (missing.length > 0) {
        throw new Error(`[csp] vercel.json connect-src is missing ${missing.join(", ")}. Update the CSP for this deployment.`);
      }
    },
  };
}

// Headers for the local dev/preview servers. The CSP is left to Vercel because the dev server
// needs inline React-refresh scripts and the deployment origins differ locally.
const LOCAL_HEADERS = (() => {
  const { "Content-Security-Policy": _csp, "Strict-Transport-Security": _hsts, ...rest } = vercelHeaders();
  return { ...rest, "Cache-Control": "no-store" };
})();

export default defineConfig({
  plugins: [react(), cspDeploymentGuard()],
  build: {
    sourcemap: false, // no public source maps (T1873)
    target: "es2022",
    assetsInlineLimit: 0, // no data: script/font assets; everything is served from 'self'
  },
  server: {
    port: 5173,
    strictPort: true,
    headers: LOCAL_HEADERS,
  },
  preview: {
    headers: LOCAL_HEADERS,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
    env: {
      VITE_SUPABASE_URL: "https://example.supabase.co",
      VITE_SUPABASE_ANON_KEY: "test-anon-key",
      VITE_API_BASE_URL: "https://api.example.test",
    },
  },
});
