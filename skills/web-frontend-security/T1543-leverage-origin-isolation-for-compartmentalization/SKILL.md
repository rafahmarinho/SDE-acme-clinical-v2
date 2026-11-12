---
name: t1543-leverage-origin-isolation-for-compartmentalization
description: Uses browser origin isolation for ACME Clinical: separate origins for the SPA, the FastAPI API and Supabase, user-uploaded files served only from the Supabase Storage origin, and any optional third-party 3D visualization isolated in its own origin rather than running with access to the clinical session.
---

# T1543: Leverage origin isolation for compartmentalization

**Category:** CODE_FIX
**SD Elements:** [T1543](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T1543/)
**Priority:** 5/10 · **Phase:** architecture-design

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe (pode criar algo bem visual em 3D se"
> (EN: limit settings, reports and team management (you may create something very visual in 3D if)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
A developer might pull a 3D scene builder or viewer (or its CDN scripts) straight into the main SPA, and might serve uploaded files or generated reports from the same origin as the app. Any bug or malicious code in that component then runs with full access to the Supabase session in `localStorage` and every patient record the user can see.

**Secure Implementation Pattern:**
Origin map (document in README):
```json
{
  "web (trusted UI, holds session)": "https://acme-clinical.vercel.app",
  "api (FastAPI, JSON only)":        "https://acme-clinical-api.vercel.app",
  "supabase (auth/db/realtime/files)": "https://<project-ref>.supabase.co",
  "viz (optional, untrusted 3D/3rd-party, no session)": "https://acme-clinical-viz.vercel.app"
}
```
```tsx
// frontend/src/components/IsolatedViz.tsx - only if third-party 3D code is used
export function IsolatedViz({ beds }: { beds: { id: string; status: string }[] }) {
  const ref = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    const f = ref.current; if (!f) return;
    const off = listenToViz(f, (m) => m.type === "ready" && sendToViz(f, { type: "beds", beds }));
    return off;
  }, [beds]);
  return <iframe ref={ref} title="3D ward" src={import.meta.env.VITE_VIZ_ORIGIN}
                 sandbox="allow-scripts" referrerPolicy="no-referrer" />;
}
```

**Implementation Guidance:**
- Keep the SPA and API on separate Vercel projects/origins (already planned); the API serves JSON only and no HTML.
- Never serve user-uploaded content (Storage files) from the SPA origin; download from Supabase Storage via signed URLs with `Content-Disposition: attachment`.
- Preferred 3D approach: bundle Three.js/React Three Fiber from npm (trusted, reviewed dependency) inside the SPA. If any third-party/untrusted 3D component, model loader or embed is needed, host it on a separate origin (`viz` project) and embed with `sandbox="allow-scripts"` (no `allow-same-origin`, T1544); it receives only minimal, de-identified bed status through validated `postMessage` (T258), never tokens.
- Add the viz origin to `frame-src` in the SPA CSP only if used; otherwise keep `frame-src 'none'`.
- Admin functions (team management) stay in the same SPA but are protected server-side by role checks; consider a separate admin origin if the app grows.
- Add `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Resource-Policy: same-site` on the SPA.
- Reference: SD Elements guidance for T1543.

**Success Criteria:**
- [ ] The origin map is documented in README and reflected in CSP `connect-src`/`frame-src`.
- [ ] No third-party 3D/embed code runs in the SPA origin; any such code is in a sandboxed cross-origin iframe.
- [ ] Uploaded files are never served from the SPA origin.

**Status:** Applied
