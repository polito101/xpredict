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
 *
 * Render budget: glyph strokes are batched into one path per quantized
 * brightness level (color strings come from a small LUT), so the grid pass is
 * O(levels) stroke()/style-parse calls instead of O(cells) — a 4K viewport
 * has ~7,200 cells. Resizes RETARGET the X (springs glide particles to the
 * new layout) instead of re-seeding it, and ripples are capped + advanced by
 * elapsed time so a low frame rate cannot compound their cost.
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
/** Ripples retire (and their influence fades to zero) at this fraction of the
 * viewport diagonal — past it the visual effect was negligible anyway. */
const RIPPLE_RANGE = 0.7;
const MAX_RIPPLES = 6;
const X_COUNT = 230;
const X_EXTENT = 0.36;
const X_JITTER = 13;
const X_CURSOR_RADIUS = 90;
const X_RIPPLE_BAND = 30;
const SPRING_K = 0.016;
const DAMPING = 0.88;
const LINK_DIST2 = 32 * 32;
const QPI = Math.PI / 4;
/** Brightness quantization levels for the color LUTs / glyph batching. */
const LUT_N = 32;

type RGB = readonly [number, number, number];
type GridCell = {
  bx: number;
  by: number;
  ox: number;
  oy: number;
  rot: number;
  rv: number;
};
type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  tx: number;
  ty: number;
  r: number;
};
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
    const hostEl = hostRef.current;
    const canvasEl = canvasRef.current;
    if (!hostEl || !canvasEl) return;
    const ctx2d = canvasEl.getContext("2d");
    if (!ctx2d) return;
    // Non-null aliases so the nested closures see narrowed types.
    const host: HTMLDivElement = hostEl;
    const canvas: HTMLCanvasElement = canvasEl;
    const ctx: CanvasRenderingContext2D = ctx2d;
    // Pointer events attach to the hero section (the host's parent): the
    // overlay is pointer-events-none except the CTA container, and section-
    // level listeners keep working while the cursor is over the CTAs too.
    const pointerEl: HTMLElement = host.parentElement ?? host;

    // White-label palette: brand primary, lightened for visibility on obsidian.
    const css = getComputedStyle(document.documentElement);
    const primary = parseHex(css.getPropertyValue("--brand-primary"), [79, 70, 229]);
    const lineC = lighten(primary, 0.2);
    const dotC = lighten(primary, 0.55);
    const linkC = mix(lineC, dotC, 0.5);

    // Color LUTs indexed by quantized brightness — zero string allocation and
    // O(LUT_N) style parses per frame instead of O(cells)/O(links).
    const glyphLut: string[] = [];
    const linkLut: string[] = [];
    for (let i = 0; i <= LUT_N; i++) {
      const t = i / LUT_N;
      glyphLut.push(rgba(mix(lineC, dotC, t), GRID_REST_ALPHA + t * 0.74));
      linkLut.push(rgba(linkC, t * 0.5));
    }
    const dotFill = rgba(dotC, 0.95);

    let W = 0;
    let H = 0;
    let rawDpr = 0;
    let mx = -9999;
    let my = -9999;
    let raf = 0;
    let lastT = 0;
    let grid: GridCell[] = [];
    const pts: Particle[] = [];
    const ripples: Ripple[] = [];
    // Glyph batches reused across frames (cleared via length = 0).
    const buckets: GridCell[][] = Array.from({ length: LUT_N + 1 }, () => []);

    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let reduced = mq?.matches ?? false;

    /**
     * Size the backing store and lay out grid + X targets for the current
     * host box. Existing particles are RETARGETED (springs glide them to the
     * new layout); they are seeded randomly only on first run. In-flight
     * ripples and grid motion state survive ordinary resizes.
     */
    function layout() {
      rawDpr = window.devicePixelRatio || 1;
      const dpr = Math.min(rawDpr, 2);
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
      const fresh = pts.length === 0;
      for (let i = 0; i < X_COUNT; i++) {
        const u = Math.random() * 2 - 1;
        const j = (Math.random() - 0.5) * X_JITTER;
        const onMainStroke = i % 2 === 0;
        // Jitter must be PERPENDICULAR to each stroke: the "\" stroke runs
        // along (1,1)/√2 (perpendicular (-1,1)/√2), the "/" stroke along
        // (1,-1)/√2 (perpendicular (1,1)/√2) — so both read as ~13px bands.
        const tx = cx + u * ext + (onMainStroke ? -j : j) * 0.707;
        const ty = (onMainStroke ? cy + u * ext : cy - u * ext) + j * 0.707;
        if (fresh) {
          pts.push({
            x: Math.random() * W,
            y: Math.random() * H,
            vx: 0,
            vy: 0,
            tx,
            ty,
            r: Math.random() * 1.3 + 1,
          });
        } else {
          pts[i].tx = tx;
          pts[i].ty = ty;
        }
      }
    }

    /** Append one mini-X to the current path (second stroke = first rotated
     * 90°, so cos/sin are reused instead of recomputed). */
    function addGlyphToPath(g: GridCell, half: number) {
      const px = g.bx + g.ox;
      const py = g.by + g.oy;
      const c1 = Math.cos(g.rot + QPI) * half;
      const s1 = Math.sin(g.rot + QPI) * half;
      ctx.moveTo(px - c1, py - s1);
      ctx.lineTo(px + c1, py + s1);
      ctx.moveTo(px + s1, py - c1);
      ctx.lineTo(px - s1, py + c1);
    }

    /** Stroke every batched glyph: one beginPath/strokeStyle/stroke per
     * non-empty brightness level. */
    function flushGlyphBuckets() {
      for (let bi = 0; bi <= LUT_N; bi++) {
        const bucket = buckets[bi];
        if (bucket.length === 0) continue;
        const t = bi / LUT_N;
        const half = 4 + t * 2.5;
        ctx.strokeStyle = glyphLut[bi];
        ctx.beginPath();
        for (const g of bucket) addGlyphToPath(g, half);
        ctx.stroke();
        bucket.length = 0;
      }
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
            ctx.strokeStyle = linkLut[((1 - d2 / LINK_DIST2) * LUT_N) | 0];
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.stroke();
          }
        }
        ctx.fillStyle = dotFill;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function step(dt: number) {
      ctx.clearRect(0, 0, W, H);
      const retireR = Math.sqrt(W * W + H * H) * RIPPLE_RANGE;

      // Time-based advance: a low frame rate must not extend ripple lifetime
      // (which would compound the per-ripple cost into a feedback loop).
      for (let i = ripples.length - 1; i >= 0; i--) {
        ripples[i].r += RIPPLE_SPEED * dt;
        if (ripples[i].r > retireR) ripples.splice(i, 1);
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
            const gg = (1 - band / RIPPLE_BAND) * (1 - rp.r / retireR);
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
        const bb = bright >= 1 ? 1 : bright;
        buckets[(bb * LUT_N) | 0].push(g);
      }
      flushGlyphBuckets();

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
            const g2 = (1 - band / X_RIPPLE_BAND) * (1 - rp.r / retireR) * 3.4;
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
      for (const g of grid) buckets[0].push(g);
      flushGlyphBuckets();
      for (const p of pts) {
        p.x = p.tx;
        p.y = p.ty;
      }
      drawX();
    }

    function loop(now: number) {
      // Clamp dt to [0.25, 3] frames so tab restores can't teleport ripples.
      const dt = lastT === 0 ? 1 : Math.min(Math.max((now - lastT) / 16.667, 0.25), 3);
      lastT = now;
      // A monitor change can alter devicePixelRatio without resizing the host.
      if ((window.devicePixelRatio || 1) !== rawDpr) layout();
      step(dt);
      raf = requestAnimationFrame(loop);
    }

    function start() {
      cancelAnimationFrame(raf);
      lastT = 0;
      layout();
      if (reduced) renderStatic();
      else raf = requestAnimationFrame(loop);
    }

    // Pointer input — reduced motion ignores it (the static frame never
    // changes); local coords come from the host box (identical to the
    // section's: the host is absolute inset-0).
    const toLocal = (cx: number, cy: number) => {
      const b = host.getBoundingClientRect();
      mx = cx - b.left;
      my = cy - b.top;
    };
    const clearPointer = () => {
      mx = -9999;
      my = -9999;
    };
    const pushRipple = () => {
      if (ripples.length >= MAX_RIPPLES) ripples.shift();
      ripples.push({ x: mx, y: my, r: 0 });
    };
    const onMouseMove = (e: MouseEvent) => {
      if (!reduced) toLocal(e.clientX, e.clientY);
    };
    const onMouseDown = (e: MouseEvent) => {
      if (reduced) return;
      toLocal(e.clientX, e.clientY);
      pushRipple();
    };
    const onTouchStart = (e: TouchEvent) => {
      if (reduced || !e.touches[0]) return;
      toLocal(e.touches[0].clientX, e.touches[0].clientY);
      pushRipple();
    };
    const onTouchMove = (e: TouchEvent) => {
      if (!reduced && e.touches[0]) toLocal(e.touches[0].clientX, e.touches[0].clientY);
    };
    pointerEl.addEventListener("mousemove", onMouseMove);
    pointerEl.addEventListener("mouseleave", clearPointer);
    pointerEl.addEventListener("mousedown", onMouseDown);
    pointerEl.addEventListener("touchstart", onTouchStart, { passive: true });
    pointerEl.addEventListener("touchmove", onTouchMove, { passive: true });
    pointerEl.addEventListener("touchend", clearPointer);

    const onMqChange = (e: MediaQueryListEvent) => {
      reduced = e.matches;
      clearPointer();
      start();
    };
    mq?.addEventListener("change", onMqChange);

    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      // Skip no-op observations (incl. the mandatory initial one — start()
      // below already laid the canvas out).
      ro = new ResizeObserver(() => {
        if (host.clientWidth !== W || host.clientHeight !== H) start();
      });
      ro.observe(host);
    }

    start();

    return () => {
      cancelAnimationFrame(raf);
      mq?.removeEventListener("change", onMqChange);
      ro?.disconnect();
      pointerEl.removeEventListener("mousemove", onMouseMove);
      pointerEl.removeEventListener("mouseleave", clearPointer);
      pointerEl.removeEventListener("mousedown", onMouseDown);
      pointerEl.removeEventListener("touchstart", onTouchStart);
      pointerEl.removeEventListener("touchmove", onTouchMove);
      pointerEl.removeEventListener("touchend", clearPointer);
    };
  }, []);

  return (
    <div ref={hostRef} aria-hidden="true" className="absolute inset-0">
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}
