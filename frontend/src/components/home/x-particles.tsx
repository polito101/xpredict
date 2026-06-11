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
