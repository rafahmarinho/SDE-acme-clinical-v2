// Web front-end security regression suite (SD Elements, skills/web-frontend-security).
// Static checks over the Vercel deployment config, index.html, tsconfig and the SPA source, plus
// behavioural tests of the opener-isolation helpers. See docs/security/web-frontend.md.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import vercelRaw from "../vercel.json?raw";
import indexHtml from "../index.html?raw";
import tsconfigAppRaw from "../tsconfig.app.json?raw";
import packageRaw from "../package.json?raw";
import { ExternalLink, openSafely, safeExternalUrl } from "./components/ExternalLink";
import { SearchFilterBar } from "./components/SearchFilterBar";

interface HeaderRule {
  source: string;
  headers: { key: string; value: string }[];
}
const vercel = JSON.parse(vercelRaw) as { headers: HeaderRule[]; rewrites: { source: string; destination: string }[] };

function rule(source: string): Record<string, string> {
  const found = vercel.headers.find((r) => r.source === source);
  if (!found) throw new Error(`no header rule for ${source}`);
  return Object.fromEntries(found.headers.map((h) => [h.key.toLowerCase(), h.value]));
}
const all = rule("/(.*)");
const html = rule("/((?!assets/).*)");
const assets = rule("/assets/(.*)");
const csp = all["content-security-policy"] ?? "";
const directive = (name: string): string[] | undefined => {
  const d = csp.split(";").map((s) => s.trim()).find((s) => s === name || s.startsWith(`${name} `));
  return d?.split(/\s+/).slice(1);
};

// Source files of the SPA (tests excluded): raw text keyed by path relative to src/.
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(import.meta.glob(["./**/*.{ts,tsx}", "!./**/*.test.{ts,tsx}", "!./test/**"], {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>).map(([path, text]) => [path.replace(/^\.\//, ""), text]),
);
const sourcesMatching = (re: RegExp, except: string[] = []) =>
  Object.entries(SOURCES)
    .filter(([path, text]) => !except.includes(path) && re.test(text))
    .map(([path]) => path);

describe("Content-Security-Policy (T331, T332, T1469, T1543)", () => {
  it("defines every required directive", () => {
    for (const d of ["default-src", "script-src", "style-src", "connect-src", "img-src", "form-action",
      "frame-ancestors", "frame-src", "object-src", "base-uri", "report-uri", "report-to"]) {
      expect(directive(d), d).toBeDefined();
    }
    expect(directive("upgrade-insecure-requests")).toEqual([]);
  });

  it("script-src and style-src forbid inline code, eval and wildcards", () => {
    for (const d of ["script-src", "style-src", "default-src"]) {
      const values = directive(d) ?? [];
      expect(values, d).toEqual(["'self'"]);
    }
  });

  it("forbids framing, plugins, base-tag hijacking and cross-site form posts", () => {
    expect(directive("frame-ancestors")).toEqual(["'none'"]);
    expect(directive("frame-src")).toEqual(["'none'"]);
    expect(directive("object-src")).toEqual(["'none'"]);
    expect(directive("base-uri")).toEqual(["'self'"]);
    expect(directive("form-action")).toEqual(["'self'"]);
  });

  it("connect-src is an explicit allow-list: API origin plus Supabase https and wss", () => {
    const connect = directive("connect-src") ?? [];
    expect(connect[0]).toBe("'self'");
    const origins = connect.slice(1);
    expect(origins.length).toBe(3);
    for (const o of origins) {
      expect(o).not.toMatch(/\*/);
      expect(new URL(o).origin).toBe(o); // bare origin, no scheme-only source like "https:"
    }
    const supabase = origins.filter((o) => /\.supabase\.co$/.test(o));
    expect(supabase.map((o) => new URL(o).protocol).sort()).toEqual(["https:", "wss:"]);
    expect(new URL(supabase[0]!).host).toBe(new URL(supabase[1]!).host);
    expect(origins.filter((o) => o.startsWith("http:") || o.startsWith("ws:"))).toEqual([]);
  });

  it("reports violations only to the ACME Clinical API (T1469)", () => {
    const [reportUri] = directive("report-uri") ?? [];
    const api = (directive("connect-src") ?? []).find((o) => !o.includes("supabase") && o !== "'self'");
    expect(new URL(reportUri!).origin).toBe(api);
    expect(new URL(reportUri!).pathname).toBe("/v1/csp-report");
    expect(all["reporting-endpoints"]).toBe(`csp="${reportUri}"`);
    expect(directive("report-to")).toEqual(["csp"]);
  });
});

describe("transport, framing, sniffing and isolation headers", () => {
  it("HSTS for at least one year (T322, T333)", () => {
    const hsts = all["strict-transport-security"] ?? "";
    expect(Number(/max-age=(\d+)/.exec(hsts)?.[1])).toBeGreaterThanOrEqual(31536000);
  });

  it("clickjacking: X-Frame-Options DENY plus frame-ancestors (T119)", () => {
    expect(all["x-frame-options"]).toBe("DENY");
    expect(csp).toMatch(/frame-ancestors 'none'/);
  });

  it("nosniff on every route, including assets (T435, T436)", () => {
    expect(all["x-content-type-options"]).toBe("nosniff");
  });

  it("referrer, permissions, opener and resource policies (T219, T512, T1543)", () => {
    expect(["strict-origin-when-cross-origin", "no-referrer", "same-origin"]).toContain(all["referrer-policy"]);
    for (const feature of ["camera", "microphone", "geolocation", "payment", "usb"]) {
      expect(all["permissions-policy"]).toContain(`${feature}=()`);
    }
    expect(all["cross-origin-opener-policy"]).toBe("same-origin");
    expect(all["cross-origin-resource-policy"]).toBe("same-site");
  });

  it("index.html and SPA routes are never cached; only hashed assets are (T64, T112)", () => {
    expect(html["cache-control"]).toMatch(/no-store/);
    expect(html["cache-control"]).toMatch(/must-revalidate/);
    expect(html["pragma"]).toBe("no-cache");
    expect(html["expires"]).toBe("0");
    expect(assets["cache-control"]).toMatch(/immutable/);
    expect(all["cache-control"]).toBeUndefined();
  });

  it("missing assets are not rewritten to index.html", () => {
    expect(vercel.rewrites).toEqual([{ source: "/((?!assets/).*)", destination: "/index.html" }]);
  });

  it("no header discloses technology or versions (T1873, T1874)", () => {
    const keys = vercel.headers.flatMap((r) => r.headers.map((h) => h.key.toLowerCase()));
    for (const leaky of ["x-powered-by", "server", "x-app-version", "x-runtime", "x-debug", "via"]) {
      expect(keys).not.toContain(leaky);
    }
    for (const value of vercel.headers.flatMap((r) => r.headers.map((h) => h.value))) {
      expect(value).not.toMatch(/\b(react|vite|node)\/?\s*\d+\.\d+/i);
    }
  });
});

describe("index.html, encoding and strict mode (T44, T132, T325, T329)", () => {
  it("declares UTF-8 once, as the first element in <head>", () => {
    const head = indexHtml.slice(0, 1024).toLowerCase();
    expect(head).toMatch(/<head>\s*<meta charset="utf-8"\s*\/?>/);
    expect(indexHtml.toLowerCase().match(/charset=/g)?.length).toBe(1);
  });

  it("loads only external ES module scripts (strict by spec, CSP script-src 'self')", () => {
    const scripts = [...indexHtml.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
    expect(scripts.length).toBeGreaterThan(0);
    for (const [, attrs, body] of scripts) {
      expect(attrs).toMatch(/type="module"/);
      expect(attrs).toMatch(/src="\/[^"]+"/);
      expect(body!.trim()).toBe("");
    }
    expect(indexHtml).not.toMatch(/\son[a-z]+=/i); // no inline event handlers
  });

  it("TypeScript strict mode is on and the package is an ES module", () => {
    const ts = JSON.parse(tsconfigAppRaw) as { compilerOptions: { strict?: boolean; alwaysStrict?: boolean } };
    expect(ts.compilerOptions.strict).toBe(true);
    expect(ts.compilerOptions.alwaysStrict ?? ts.compilerOptions.strict).toBe(true);
    expect((JSON.parse(packageRaw) as { type?: string }).type).toBe("module");
  });

  it("no classic (non-module) scripts or eval-like code in src", () => {
    expect(sourcesMatching(/\beval\s*\(|new\s+Function\s*\(|setTimeout\(\s*["'`]/)).toEqual([]);
    expect(sourcesMatching(/dangerouslySetInnerHTML|\.innerHTML\s*=|outerHTML\s*=|document\.write\(/)).toEqual([]);
  });
});

describe("web messaging and untrusted content (T258, T319, T1543, T1544)", () => {
  it("no postMessage senders or unmanaged message listeners", () => {
    expect(Object.keys(SOURCES)).toContain("screens/PatientDetail.tsx"); // the scan really covers src/
    expect(Object.keys(SOURCES).some((p) => p.endsWith(".test.tsx"))).toBe(false);
    // Cross-window messaging (window/iframe/opener/parent) is forbidden. Same-origin BroadcastChannel
    // (used by auth/session.ts to sync sign-out across tabs) is not cross-domain messaging.
    expect(sourcesMatching(/\b(window|self|top|parent|opener|contentWindow|source)\s*\??\.\s*postMessage\s*\(|postMessage\([^)]*["'`]\*["'`]/)).toEqual([]);
    expect(sourcesMatching(/(window\.|^|\s)addEventListener\(\s*["'`]message["'`]|window\.onmessage\s*=/m)).toEqual([]);
    for (const [path, text] of Object.entries(SOURCES)) {
      if (/\bonmessage\s*=|postMessage\s*\(/.test(text)) expect(text, path).toMatch(/new BroadcastChannel\(/);
    }
  });

  it("every iframe is sandboxed and never with allow-scripts + allow-same-origin", () => {
    for (const [path, text] of Object.entries(SOURCES)) {
      for (const [tag] of text.matchAll(/<iframe\b[\s\S]*?>/g)) {
        expect(tag, path).toMatch(/\bsandbox=/);
        expect(/allow-scripts/.test(tag) && /allow-same-origin/.test(tag), path).toBe(false);
      }
    }
  });
});

describe("opener isolation (T512, T513)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("target=_blank and window.open are used only through ExternalLink", () => {
    expect(sourcesMatching(/target=["{]["']?_blank/, ["components/ExternalLink.tsx"])).toEqual([]);
    expect(sourcesMatching(/window\.open\s*\(/, ["components/ExternalLink.tsx"])).toEqual([]);
  });

  it("ExternalLink always sets noopener noreferrer and blocks unsafe schemes", () => {
    render(<ExternalLink href="https://example.org/manual">Manual</ExternalLink>);
    const link = screen.getByRole("link", { name: "Manual" });
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("target")).toBe("_blank");
    render(<ExternalLink href="javascript:alert(1)">Bad</ExternalLink>);
    expect(screen.queryByRole("link", { name: "Bad" })).toBeNull();
    expect(safeExternalUrl("http://example.org")).toBeNull();
    expect(safeExternalUrl("data:text/html,<script>1</script>")).toBeNull();
  });

  it("openSafely passes noopener,noreferrer and nulls the opener", () => {
    const fake = { opener: {} } as unknown as Window;
    const spy = vi.spyOn(window, "open").mockReturnValue(fake);
    openSafely("https://example.supabase.co/storage/v1/object/sign/x?token=t", "https://example.supabase.co");
    expect(spy.mock.calls[0]?.[1]).toBe("_blank");
    expect(spy.mock.calls[0]?.[2]).toBe("noopener,noreferrer");
    expect(fake.opener).toBeNull();
  });

  it("openSafely refuses other origins and non-HTTPS URLs", () => {
    const spy = vi.spyOn(window, "open").mockReturnValue(null);
    expect(() => openSafely("https://evil.example/x", "https://example.supabase.co")).toThrow();
    expect(() => openSafely("https://example.supabase.co.evil.example/x", "https://example.supabase.co")).toThrow();
    expect(() => openSafely("http://example.supabase.co/x")).toThrow();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("confidential fields and client-side storage (T63, T111, T296, T219)", () => {
  const CONFIDENTIAL_SCREENS = ["WardOverview", "PatientList", "PatientDetail", "LiveMonitoring", "Alarms", "Devices",
    "Thresholds", "Reports", "Simulation", "Events"].map((s) => `screens/${s}.tsx`);
  const COMPONENTS = Object.keys(SOURCES).filter((p) => p.startsWith("components/"));

  it("search box disables autocomplete, autocorrect and spellcheck", () => {
    render(<SearchFilterBar onSearch={() => undefined} />);
    const box = screen.getByRole("searchbox");
    expect(box.getAttribute("autocomplete")).toBe("off");
    expect(box.getAttribute("spellcheck")).toBe("false");
    fireEvent.change(box, { target: { value: "Demo Patient" } });
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
  });

  it("every form and free-text field in clinical screens has autocomplete off", () => {
    for (const path of [...CONFIDENTIAL_SCREENS, ...COMPONENTS]) {
      const text = SOURCES[path];
      expect(text, path).toBeDefined();
      for (const [tag] of text!.matchAll(/<form\b[^>]*>/g)) expect(tag, path).toMatch(/autoComplete="off"/);
      for (const [tag] of text!.matchAll(/<(?:input|textarea)\b[\s\S]*?\/>/g)) {
        if (/type="(checkbox|radio|file|hidden)"/.test(tag)) continue;
        // Password inputs follow the documented password-manager decision instead.
        if (/type=\{visible \? "text" : "password"\}|type="password"/.test(tag)) {
          expect(path === "components/PasswordField.tsx" ? text : tag, path).toMatch(/"current-password" \| "new-password"|autoComplete="(current|new)-password"/);
          continue;
        }
        expect(tag, path).toMatch(/autoComplete="off"/);
      }
    }
  });

  it("login and password reset follow the documented password-manager decision", () => {
    expect(SOURCES["screens/Login.tsx"]).toMatch(/autoComplete="current-password"/);
    expect(SOURCES["screens/Login.tsx"]).toMatch(/autoComplete="username"/);
    expect(SOURCES["screens/ResetPassword.tsx"]).toMatch(/autoComplete="new-password"/);
  });

  it("clinical data is never persisted in web storage, IndexedDB or Cache Storage", () => {
    // lib/supabase.ts holds the Supabase session; auth/session.ts wipes storage on sign-out and keeps
    // only a one-shot, non-personal sign-out reason code.
    expect(sourcesMatching(/\b(localStorage|sessionStorage|indexedDB)\b|caches\.open|serviceWorker\.register/,
      ["lib/supabase.ts", "auth/session.ts"])).toEqual([]);
    const writes = [...(SOURCES["auth/session.ts"] ?? "").matchAll(/(?:localStorage|sessionStorage)\.setItem\(([^,]+),/g)];
    for (const [, key] of writes) expect(key!.trim()).toBe("SIGNED_OUT_KEY");
    expect(SOURCES["auth/session.ts"] ?? "").not.toMatch(/indexedDB\.open\(|caches\.open\(/);
  });

  it("patient search text stays out of the browser URL", () => {
    expect(SOURCES["screens/PatientList.tsx"]).not.toMatch(/\.set\(\s*["']q["']/);
  });
});
