# Home X-Grid Hero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 7-section landing with a single-viewport interactive hero — a particle "X" over a grid of mini brand-X glyphs with a click-triggered ripple (spec: `docs/superpowers/specs/2026-06-11-home-x-grid-hero-design.md`).

**Architecture:** One Server Component section (`XGridHero`) renders overlay copy + CTAs over one Client Component (`XParticles`) that owns a full-bleed transparent canvas (the Aurora backdrop shows through). All physics/render constants come from the approved prototype. The old home sections and their dead `hv-*` CSS are deleted.

**Tech Stack:** Next.js 15 App Router, React 19, Tailwind 4, canvas 2D (no new deps), vitest + testing-library (jsdom).

**Environment notes:**
- Run all frontend commands from `frontend/` with the **standalone pnpm 9.15.0** — NEVER `corepack pnpm` (resolves to destructive 11.x).
- Work happens on branch `gsd/home-x-grid-hero` in the worktree `.claude/worktrees/home-x-grid-hero` (the main checkout is in use by a concurrent session — do not touch it).

**File structure:**
- Create: `frontend/src/components/home/x-particles.tsx` — client canvas effect (one responsibility: draw/animate)
- Create: `frontend/src/components/home/x-particles.test.tsx`
- Create: `frontend/src/components/home/x-grid-hero.tsx` — server hero section (layout + copy + CTAs)
- Create: `frontend/src/components/home/x-grid-hero.test.tsx`
- Rewrite: `frontend/src/app/page.tsx`
- Delete: `frontend/src/components/home/{hero-band,hero-visual,pillars,capability-grid,api-section,demo-showcase,how-it-works,landing-cta}.tsx`
- Modify: `frontend/src/app/globals.css` — remove dead `hv-*` keyframes/utilities

---

### Task 1: `XParticles` client canvas component

**Files:**
- Create: `frontend/src/components/home/x-particles.tsx`
- Test: `frontend/src/components/home/x-particles.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
/**
 * XParticles smoke tests. jsdom has no real canvas/matchMedia/ResizeObserver,
 * so all three are stubbed; assertions target lifecycle behavior (loop vs
 * static frame, cleanup), not pixels.
 */
import { cleanup, render } from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
  type MockInstance,
} from "vitest";

import { XParticles } from "./x-particles";

type MqListener = (e: { matches: boolean }) => void;

function makeFakeCtx() {
  return {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 1,
  };
}

function stubMatchMedia(reduced: boolean) {
  const addEventListener = vi.fn<(t: string, l: MqListener) => void>();
  const removeEventListener = vi.fn();
  window.matchMedia = vi.fn().mockReturnValue({
    matches: reduced,
    addEventListener,
    removeEventListener,
  } as unknown as MediaQueryList) as unknown as typeof window.matchMedia;
  return { addEventListener, removeEventListener };
}

class FakeResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
}

describe("XParticles", () => {
  let fakeCtx: ReturnType<typeof makeFakeCtx>;
  let rafSpy: MockInstance<typeof window.requestAnimationFrame>;
  let cafSpy: MockInstance<typeof window.cancelAnimationFrame>;

  beforeEach(() => {
    fakeCtx = makeFakeCtx();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      fakeCtx as unknown as CanvasRenderingContext2D,
    );
    rafSpy = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(1);
    cafSpy = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("mounts an aria-hidden canvas and starts the animation loop", () => {
    stubMatchMedia(false);
    const { container } = render(<XParticles />);
    const canvas = container.querySelector("canvas");
    expect(canvas).not.toBeNull();
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
    expect(rafSpy).toHaveBeenCalled();
  });

  it("draws a single static frame (no loop) under prefers-reduced-motion", () => {
    stubMatchMedia(true);
    render(<XParticles />);
    expect(rafSpy).not.toHaveBeenCalled();
    expect(fakeCtx.clearRect).toHaveBeenCalledTimes(1);
  });

  it("cleans up rAF and media-query listener on unmount", () => {
    const mq = stubMatchMedia(false);
    const { unmount } = render(<XParticles />);
    unmount();
    expect(cafSpy).toHaveBeenCalled();
    expect(mq.removeEventListener).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/home/x-particles.test.tsx`
Expected: FAIL — `Cannot find module './x-particles'` (or equivalent resolve error).

- [ ] **Step 3: Write the implementation**

```tsx
/**
 * XParticles — the landing's interactive canvas (single-viewport hero).
 *
 * Two layers on one transparent canvas (the Aurora backdrop shows through):
 *  - A grid of mini brand-X glyphs (±45° crosses), near-invisible at rest.
 *    The cursor displaces/brightens nearby glyphs; a click/tap launches a
 *    ripple ring that pushes, brightens, and spins glyphs as it passes.
 *  - A particle "X" (~230 points spring-bound to the two diagonal strokes of
 *    the brand mark) wired as a network (links between close pairs). The
 *    cursor scatters it locally; ripples knock it; springs always re-form it.
 *
 * White-label: colors derive from `--brand-primary` at mount (lightened for
 * lines/dots), so an operator palette change re-tints the effect for free.
 * Reduced motion: one static frame, no loop, pointer input ignored.
 * Decorative only (`aria-hidden`); the overlay content never depends on it.
 */
"use client";

import { useEffect, useRef } from "react";

const GRID_GAP = 34;
const GRID_REST_ALPHA = 0.16;
const GRID_CURSOR_RADIUS = 110;
const GRID_CURSOR_PUSH = 12;
const GRID_RIPPLE_PUSH = 16;
const RIPPLE_SPEED = 4.5;
const RIPPLE_BAND = 28;
const X_COUNT = 230;
const X_EXTENT = 0.36;
const X_JITTER = 13;
const X_CURSOR_RADIUS = 90;
const X_RIPPLE_BAND = 30;
const SPRING_K = 0.016;
const DAMPING = 0.88;
const LINK_DIST2 = 32 * 32;
const QPI = Math.PI / 4;

type RGB = readonly [number, number, number];
type GridCell = { bx: number; by: number; ox: number; oy: number; rot: number; rv: number };
type Particle = { x: number; y: number; vx: number; vy: number; tx: number; ty: number; r: number };
type Ripple = { x: number; y: number; r: number };

function parseHex(value: string, fallback: RGB): RGB {
  const m = /^#?([0-9a-f]{6})$/i.exec(value.trim());
  if (!m) return fallback;
  const n = Number.parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function lighten([r, g, b]: RGB, t: number): RGB {
  return [
    Math.round(r + (255 - r) * t),
    Math.round(g + (255 - g) * t),
    Math.round(b + (255 - b) * t),
  ];
}

function mix(a: RGB, b: RGB, t: number): RGB {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

function rgba([r, g, b]: RGB, a: number): string {
  return `rgba(${r},${g},${b},${a.toFixed(3)})`;
}

export function XParticles() {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // White-label palette: brand primary, lightened for visibility on obsidian.
    const css = getComputedStyle(document.documentElement);
    const primary = parseHex(css.getPropertyValue("--brand-primary"), [79, 70, 229]);
    const lineC = lighten(primary, 0.2);
    const dotC = lighten(primary, 0.55);
    const linkC = mix(lineC, dotC, 0.5);

    let W = 0;
    let H = 0;
    let mx = -9999;
    let my = -9999;
    let raf = 0;
    let grid: GridCell[] = [];
    let pts: Particle[] = [];
    let ripples: Ripple[] = [];

    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let reduced = mq?.matches ?? false;

    function rebuild() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = host.clientWidth;
      H = host.clientHeight;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      grid = [];
      for (let y = GRID_GAP / 2; y < H; y += GRID_GAP)
        for (let x = GRID_GAP / 2; x < W; x += GRID_GAP)
          grid.push({ bx: x, by: y, ox: 0, oy: 0, rot: 0, rv: 0 });

      const cx = W / 2;
      const cy = H / 2;
      const ext = Math.min(W, H) * X_EXTENT;
      pts = [];
      for (let i = 0; i < X_COUNT; i++) {
        const u = Math.random() * 2 - 1;
        const j = (Math.random() - 0.5) * X_JITTER;
        const onMainStroke = i % 2 === 0;
        pts.push({
          x: Math.random() * W,
          y: Math.random() * H,
          vx: 0,
          vy: 0,
          tx: cx + u * ext - j * 0.707,
          ty: (onMainStroke ? cy + u * ext : cy - u * ext) + j * 0.707,
          r: Math.random() * 1.3 + 1,
        });
      }
      ripples = [];
    }

    function drawGlyph(g: GridCell, bb: number) {
      const px = g.bx + g.ox;
      const py = g.by + g.oy;
      const half = 4 + bb * 2.5;
      const a1 = g.rot + QPI;
      const a2 = g.rot + 3 * QPI;
      const c1 = Math.cos(a1) * half;
      const s1 = Math.sin(a1) * half;
      const c2 = Math.cos(a2) * half;
      const s2 = Math.sin(a2) * half;
      ctx.strokeStyle = rgba(mix(lineC, dotC, bb), GRID_REST_ALPHA + bb * 0.74);
      ctx.beginPath();
      ctx.moveTo(px - c1, py - s1);
      ctx.lineTo(px + c1, py + s1);
      ctx.moveTo(px - c2, py - s2);
      ctx.lineTo(px + c2, py + s2);
      ctx.stroke();
    }

    function drawX() {
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        for (let j = i + 1; j < pts.length; j++) {
          const q = pts[j];
          const dx = p.x - q.x;
          const dy = p.y - q.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < LINK_DIST2) {
            ctx.strokeStyle = rgba(linkC, (1 - d2 / LINK_DIST2) * 0.5);
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.stroke();
          }
        }
        ctx.fillStyle = rgba(dotC, 0.95);
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function step() {
      ctx.clearRect(0, 0, W, H);
      const maxR = Math.sqrt(W * W + H * H);

      for (let i = ripples.length - 1; i >= 0; i--) {
        ripples[i].r += RIPPLE_SPEED;
        if (ripples[i].r > maxR) ripples.splice(i, 1);
      }

      ctx.lineWidth = 1;
      for (const g of grid) {
        let tox = 0;
        let toy = 0;
        let bright = 0;
        const dx = g.bx - mx;
        const dy = g.by - my;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < GRID_CURSOR_RADIUS && d > 0.5) {
          const f = (GRID_CURSOR_RADIUS - d) / GRID_CURSOR_RADIUS;
          tox += (dx / d) * f * GRID_CURSOR_PUSH;
          toy += (dy / d) * f * GRID_CURSOR_PUSH;
          bright = f * 0.7;
        }
        for (const rp of ripples) {
          const rdx = g.bx - rp.x;
          const rdy = g.by - rp.y;
          const rd = Math.sqrt(rdx * rdx + rdy * rdy);
          const band = Math.abs(rd - rp.r);
          if (band < RIPPLE_BAND && rd > 0.5) {
            const gg = (1 - band / RIPPLE_BAND) * (1 - rp.r / maxR);
            tox += (rdx / rd) * gg * GRID_RIPPLE_PUSH;
            toy += (rdy / rd) * gg * GRID_RIPPLE_PUSH;
            g.rv += gg * 0.22;
            if (gg > bright) bright = gg;
          }
        }
        g.ox += (tox - g.ox) * 0.14;
        g.oy += (toy - g.oy) * 0.14;
        g.rot += g.rv;
        g.rv *= 0.9;
        g.rot *= 0.94;
        drawGlyph(g, Math.min(1, bright));
      }

      for (const p of pts) {
        p.vx += (p.tx - p.x) * SPRING_K;
        p.vy += (p.ty - p.y) * SPRING_K;
        const dx = p.x - mx;
        const dy = p.y - my;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < X_CURSOR_RADIUS && d > 0.5) {
          const f = ((X_CURSOR_RADIUS - d) / X_CURSOR_RADIUS) * 1.5;
          p.vx += (dx / d) * f;
          p.vy += (dy / d) * f;
        }
        for (const rp of ripples) {
          const rdx = p.x - rp.x;
          const rdy = p.y - rp.y;
          const rd = Math.sqrt(rdx * rdx + rdy * rdy);
          const band = Math.abs(rd - rp.r);
          if (band < X_RIPPLE_BAND && rd > 0.5) {
            const g2 = (1 - band / X_RIPPLE_BAND) * (1 - rp.r / maxR) * 3.4;
            p.vx += (rdx / rd) * g2;
            p.vy += (rdy / rd) * g2;
          }
        }
        p.vx *= DAMPING;
        p.vy *= DAMPING;
        p.x += p.vx;
        p.y += p.vy;
      }
      drawX();
    }

    function renderStatic() {
      ctx.clearRect(0, 0, W, H);
      ctx.lineWidth = 1;
      for (const g of grid) drawGlyph(g, 0);
      for (const p of pts) {
        p.x = p.tx;
        p.y = p.ty;
      }
      drawX();
    }

    function loop() {
      step();
      raf = requestAnimationFrame(loop);
    }

    function start() {
      cancelAnimationFrame(raf);
      rebuild();
      if (reduced) renderStatic();
      else raf = requestAnimationFrame(loop);
    }

    // Pointer input — listeners live on the host wrapper; the hero overlay is
    // pointer-events-none (except CTAs), so moves/clicks land here. Reduced
    // motion ignores input entirely (the static frame never changes).
    const toLocal = (cx: number, cy: number) => {
      const b = host.getBoundingClientRect();
      mx = cx - b.left;
      my = cy - b.top;
    };
    const clearPointer = () => {
      mx = -9999;
      my = -9999;
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!reduced) toLocal(e.clientX, e.clientY);
    };
    const onMouseDown = (e: MouseEvent) => {
      if (reduced) return;
      toLocal(e.clientX, e.clientY);
      ripples.push({ x: mx, y: my, r: 0 });
    };
    const onTouchStart = (e: TouchEvent) => {
      if (reduced || !e.touches[0]) return;
      toLocal(e.touches[0].clientX, e.touches[0].clientY);
      ripples.push({ x: mx, y: my, r: 0 });
    };
    const onTouchMove = (e: TouchEvent) => {
      if (!reduced && e.touches[0]) toLocal(e.touches[0].clientX, e.touches[0].clientY);
    };
    host.addEventListener("mousemove", onMouseMove);
    host.addEventListener("mouseleave", clearPointer);
    host.addEventListener("mousedown", onMouseDown);
    host.addEventListener("touchstart", onTouchStart, { passive: true });
    host.addEventListener("touchmove", onTouchMove, { passive: true });
    host.addEventListener("touchend", clearPointer);

    const onMqChange = (e: MediaQueryListEvent) => {
      reduced = e.matches;
      clearPointer();
      start();
    };
    mq?.addEventListener("change", onMqChange);

    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => start());
      ro.observe(host);
    }

    start();

    return () => {
      cancelAnimationFrame(raf);
      mq?.removeEventListener("change", onMqChange);
      ro?.disconnect();
      host.removeEventListener("mousemove", onMouseMove);
      host.removeEventListener("mouseleave", clearPointer);
      host.removeEventListener("mousedown", onMouseDown);
      host.removeEventListener("touchstart", onTouchStart);
      host.removeEventListener("touchmove", onTouchMove);
      host.removeEventListener("touchend", clearPointer);
    };
  }, []);

  return (
    <div ref={hostRef} aria-hidden="true" className="absolute inset-0">
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}
```

Note for the implementer: in reduced-motion mode `clearRect` must run exactly once (the static frame). The FakeResizeObserver in tests never fires its callback, so `start()` runs only from mount.

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/home/x-particles.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/home/x-particles.tsx frontend/src/components/home/x-particles.test.tsx
git commit -m "feat(landing): XParticles interactive canvas (mini-X grid + particle X + ripple)"
```

---

### Task 2: `XGridHero` section component

**Files:**
- Create: `frontend/src/components/home/x-grid-hero.tsx`
- Test: `frontend/src/components/home/x-grid-hero.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
/**
 * XGridHero content tests — overlay copy, CTAs, and brand-name normalization.
 * Canvas internals are covered by x-particles.test.tsx; here getContext is
 * nulled so XParticles mounts inert.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { XGridHero } from "./x-grid-hero";

describe("XGridHero", () => {
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList) as unknown as typeof window.matchMedia;
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the headline, badge, and both CTAs", () => {
    render(<XGridHero brandName="XPredict" />);
    expect(
      screen.getByRole("heading", { level: 1, name: /connects every prediction market/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Prediction-market platform")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Explore the demo" })).toHaveAttribute(
      "href",
      "/markets",
    );
  });

  it("normalizes the default brand name to XPrediction", () => {
    render(<XGridHero brandName="XPredict" />);
    expect(screen.getByText(/^XPrediction — white-label, API-first/)).toBeInTheDocument();
  });

  it("uses an operator brand name verbatim", () => {
    render(<XGridHero brandName="Acme Bets" />);
    expect(screen.getByText(/^Acme Bets — white-label, API-first/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/components/home/x-grid-hero.test.tsx`
Expected: FAIL — `Cannot find module './x-grid-hero'`.

- [ ] **Step 3: Write the implementation**

```tsx
/**
 * XGridHero — the single-viewport landing hero (sales-demo face).
 *
 * Replaces the 7-section Phase 19 landing with one screen: the XParticles
 * canvas full-bleed underneath, and a centered, minimal overlay on top —
 * badge, headline, one brand line, two CTAs. The overlay is pointer-events-
 * none (except the CTAs) so the canvas receives cursor/click interaction
 * everywhere. Server Component (composes the client XParticles/Spark).
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Spark } from "@/components/brand/spark";
import { XParticles } from "@/components/home/x-particles";

export function XGridHero({ brandName }: { brandName: string }) {
  const raw = brandName.trim();
  const name = !raw || raw === "XPredict" ? "XPrediction" : raw;
  return (
    <section className="relative flex min-h-[calc(100dvh-4rem)] items-center justify-center overflow-hidden">
      <XParticles />

      <div className="pointer-events-none relative z-10 flex max-w-3xl flex-col items-center gap-6 px-4 py-16 text-center text-balance">
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1 text-xs font-medium text-muted-foreground">
          <Spark className="h-3.5 w-3.5" />
          Prediction-market platform
        </span>

        <h1 className="font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl">
          The core that <span className="text-gradient-brand">connects</span>{" "}
          every prediction market.
        </h1>

        <p className="max-w-xl text-base text-muted-foreground sm:text-lg">
          {name} — white-label, API-first. Run native markets, integrate
          external ones, launch your own.
        </p>

        <div className="pointer-events-auto flex flex-wrap items-center justify-center gap-3 pt-2">
          <Button asChild size="lg" className="glow-brand">
            <Link href="/login">Log in</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/markets">Explore the demo</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/components/home/x-grid-hero.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/home/x-grid-hero.tsx frontend/src/components/home/x-grid-hero.test.tsx
git commit -m "feat(landing): XGridHero single-viewport hero section"
```

---

### Task 3: Rewrite `page.tsx`

**Files:**
- Modify: `frontend/src/app/page.tsx` (full rewrite)

- [ ] **Step 1: Replace the file content**

```tsx
/**
 * Landing — the public XPredict homepage: a single-viewport interactive hero.
 *
 * Visual-first sales-demo face (see docs/superpowers/specs/
 * 2026-06-11-home-x-grid-hero-design.md): one screen, the XParticles canvas,
 * minimal copy, two CTAs. The only backend read is the public branding (best-
 * effort — the landing renders with defaults even if the backend is down).
 */
import { XGridHero } from "@/components/home/x-grid-hero";
import { fetchBrandingPublic, DEFAULT_BRANDING } from "@/lib/branding-public";

export default async function Landing() {
  let brandName = DEFAULT_BRANDING.brand_name;
  try {
    brandName = (await fetchBrandingPublic()).brand_name;
  } catch {
    // Backend unreachable — keep the default brand; the landing must render.
  }
  return <XGridHero brandName={brandName} />;
}
```

- [ ] **Step 2: Typecheck and run the whole suite**

Run: `pnpm typecheck && pnpm vitest run`
Expected: typecheck clean; all tests pass (the old home components still exist but are now unimported — that's fine until Task 4).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat(landing): single-viewport landing page (hero only)"
```

---

### Task 4: Delete the old home sections + dead `hv-*` CSS

**Files:**
- Delete: `frontend/src/components/home/hero-band.tsx`, `hero-visual.tsx`, `pillars.tsx`, `capability-grid.tsx`, `api-section.tsx`, `demo-showcase.tsx`, `how-it-works.tsx`, `landing-cta.tsx`
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Verify nothing else imports the doomed components**

Run from `frontend/`:
```bash
grep -rn "hero-band\|hero-visual\|pillars\|capability-grid\|api-section\|demo-showcase\|how-it-works\|landing-cta" src --include="*.tsx" --include="*.ts"
```
Expected: zero matches outside the files being deleted themselves. If anything else matches, STOP and report.

- [ ] **Step 2: Delete the eight components**

```bash
git rm frontend/src/components/home/hero-band.tsx frontend/src/components/home/hero-visual.tsx frontend/src/components/home/pillars.tsx frontend/src/components/home/capability-grid.tsx frontend/src/components/home/api-section.tsx frontend/src/components/home/demo-showcase.tsx frontend/src/components/home/how-it-works.tsx frontend/src/components/home/landing-cta.tsx
```

- [ ] **Step 3: Prune dead CSS in `globals.css`**

`hv-*` was only consumed by `hero-visual.tsx` (verified 2026-06-11). Remove:
1. The keyframes block: `@keyframes hv-orbit`, `hv-orbit-rev`, `hv-flow`, `hv-pulse`, `hv-core`, `hv-packet`, `hv-twinkle`, `hv-ring`, `hv-drift`, `hv-star` (currently lines ~133–242, including the comment `/* Hero living-network motion ... */`).
2. The utility classes inside `@layer utilities`: `.hv-orbit`, `.hv-orbit-rev`, `.hv-flow`, `.hv-pulse`, `.hv-core`, `.hv-packet`, `.hv-twinkle`, `.hv-ring`, `.hv-drift`, `.hv-star`, `.hv-spin`, `.hv-spin-rev` (lines ~245–297).
3. Inside the `@media (prefers-reduced-motion: reduce)` block (~line 373): remove the `.hv-*` selectors from the selector list, KEEPING `.shimmer`, `.animate-spark`, `.animate-pulse` — the block must remain:
```css
  @media (prefers-reduced-motion: reduce) {
    .shimmer,
    .animate-spark,
    .animate-pulse {
      animation: none !important;
    }
  }
```
Do NOT touch `text-gradient-brand`, `glow-brand`, `aurora`, `surface-glass`, or anything else.

- [ ] **Step 4: Verify no dangling `hv-` references and run the suite**

Run from `frontend/`:
```bash
grep -rn "hv-" src
```
Expected: zero matches.

Run: `pnpm typecheck && pnpm vitest run && pnpm lint`
Expected: all clean/green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "refactor(landing): remove old 7-section home components and dead hv-* CSS"
```
(The `git rm` deletions are already staged.)

---

### Task 5: Full verification + visual check

- [ ] **Step 1: Full frontend gate**

Run from `frontend/`: `pnpm typecheck && pnpm lint && pnpm vitest run && pnpm build`
Expected: all pass; `next build` compiles `/` as a dynamic (server-rendered) route with no errors.

- [ ] **Step 2: Visual verification (dev server)**

Start the dev server and verify in the browser preview:
- The hero fills the viewport below the nav (no content scroll; footer just below the fold).
- The mini-X grid is barely visible at rest; cursor pushes/brightens glyphs.
- Click launches a ripple (grid wave + particle-X knock); the X re-forms.
- CTAs navigate (`/login`, `/markets`) and hovering them doesn't break canvas interaction.
- No console errors; no hydration warnings.

- [ ] **Step 3: Commit any visual-tuning deltas**

If constants needed tuning during visual review, commit them:
```bash
git add frontend/src/components/home/x-particles.tsx
git commit -m "polish(landing): tune hero particle constants after visual review"
```
