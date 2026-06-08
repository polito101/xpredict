/**
 * HeroVisual — the XPrediction ecosystem core (Phase 19 → Quality Pass).
 *
 * The landing's signature piece: the "X" as the calm center of a sophisticated
 * ecosystem map. Ten ecosystem domains sit on a single, evenly-spaced ring as
 * refined icon badges; clean spokes carry a subtle energy flow inward so the
 * message reads instantly — everything routes through XPrediction.
 *
 * Quality Pass — "infrastructure running in real time" (not a casino): layered,
 * restrained motion built ENTIRELY from the design-system's existing `hv-*`
 * keyframes (already reduced-motion-safe, already SSR-safe):
 *   · a faint starfield for depth/parallax behind the network (`hv-star`);
 *   · discrete data packets that travel node → core along each spoke, so the
 *     connections read as ACTIVE routing into the hub (`hv-packet`, staggered);
 *   · pulsing "connection ports" where each wire meets the core (`hv-twinkle`);
 *   · a second, counter-rotating accent ring for quiet depth (`hv-spin-rev`);
 *   · an elevated, more luminous core so the X is unambiguously the focal point.
 *
 * Built as a hybrid for fidelity: an SVG layer draws the connections, guide ring
 * and core accent rings (crisp vector geometry + animated flow); an HTML layer
 * renders the X hub and the node badges (real CSS typography, premium glass/glow,
 * and — by living inside the container box — no clipped or overflowing labels).
 *
 * Decorative (`aria-hidden`). All motion is reduced-motion-safe (every `hv-*`
 * class is disabled under `prefers-reduced-motion`). Node/line/star coordinates
 * are rounded (trig can differ in the last ULP across engines) so SSR === CSR —
 * no hydration mismatch. Client Component (collision-free `useId`).
 */
"use client";

import { useId } from "react";
import {
  BarChart3,
  Code2,
  Database,
  Droplet,
  Globe,
  LayoutGrid,
  LineChart,
  Puzzle,
  User,
  Users,
  type LucideIcon,
} from "lucide-react";

import { LogoMark } from "@/components/brand/logo-mark";

type Node = { label: string; angle: number; Icon: LucideIcon };

// Ten ecosystem domains on one evenly-spaced ring (36° apart, clockwise from the
// top). Even spacing reads more deliberate than a scattered cloud.
const NODES: Node[] = [
  { label: "Markets", angle: 90, Icon: LineChart },
  { label: "Users", angle: 54, Icon: User },
  { label: "Liquidity", angle: 18, Icon: Droplet },
  { label: "Integrations", angle: 342, Icon: Puzzle },
  { label: "Settlement", angle: 306, Icon: Database },
  { label: "External markets", angle: 270, Icon: Globe },
  { label: "APIs", angle: 234, Icon: Code2 },
  { label: "Data", angle: 198, Icon: BarChart3 },
  { label: "Communities", angle: 162, Icon: Users },
  { label: "Platforms", angle: 126, Icon: LayoutGrid },
];

// Round to 2 decimals so coordinates serialize identically on server + client.
const r2 = (n: number) => Math.round(n * 100) / 100;

// Ring radius as a % of the container half-extent (HTML) — kept well inside the
// box so no badge or label ever touches the edge.
const RING = 36;

const points = NODES.map((n) => {
  const a = (n.angle * Math.PI) / 180;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  return {
    ...n,
    // HTML badge centre (% of container).
    left: r2(50 + RING * cos),
    top: r2(50 - RING * sin),
    // SVG spoke endpoints (viewBox 0 0 1000 1000): a clean gap at the hub and at
    // the badge, so links read as intentional routing — not lines under dots.
    x1: r2(500 + 214 * cos),
    y1: r2(500 - 214 * sin),
    x2: r2(500 + 306 * cos),
    y2: r2(500 - 306 * sin),
  };
});

// Each spoke is the same length (uniform radial), so one packet travel distance
// covers them all; +8 so the dot fully clears the hub before it fades.
const SPOKE_LEN = 306 - 214 + 8;

// Faint starfield — fixed coordinates (no Math.random → SSR-safe), kept clear of
// the central core. Pure depth/texture, like the obsidian sky behind the system.
const STARS: { cx: number; cy: number; r: number; delay: number }[] = [
  { cx: 120, cy: 160, r: 1.6, delay: 0 },
  { cx: 880, cy: 130, r: 1.3, delay: 0.8 },
  { cx: 940, cy: 420, r: 1.7, delay: 1.6 },
  { cx: 800, cy: 880, r: 1.4, delay: 0.4 },
  { cx: 470, cy: 60, r: 1.2, delay: 2.1 },
  { cx: 60, cy: 540, r: 1.5, delay: 1.2 },
  { cx: 180, cy: 860, r: 1.3, delay: 2.6 },
  { cx: 540, cy: 950, r: 1.6, delay: 0.6 },
  { cx: 930, cy: 690, r: 1.2, delay: 3.0 },
  { cx: 70, cy: 300, r: 1.3, delay: 1.9 },
  { cx: 360, cy: 905, r: 1.1, delay: 3.4 },
  { cx: 905, cy: 250, r: 1.1, delay: 2.3 },
];

const BADGE_STYLE: React.CSSProperties = {
  background: "color-mix(in oklab, var(--card) 80%, transparent)",
  boxShadow:
    "inset 0 1px 0 rgba(255,255,255,0.06), 0 2px 10px rgba(0,0,0,0.45), 0 0 22px -10px color-mix(in oklab, var(--brand-secondary) 70%, transparent)",
};

export function HeroVisual() {
  const uid = useId().replace(/:/g, "");
  const link = `hv-link-${uid}`;
  const ambient = `hv-amb-${uid}`;

  return (
    <div
      aria-hidden="true"
      className="relative mx-auto hidden aspect-square w-full max-w-[40rem] lg:block"
    >
      {/* ── Connection layer (SVG): stars, ambient lift, rings, spokes, flow ── */}
      <svg
        viewBox="0 0 1000 1000"
        className="absolute inset-0 h-full w-full"
        fill="none"
      >
        <defs>
          <linearGradient id={link} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--brand-secondary)" />
            <stop offset="100%" stopColor="var(--brand-primary)" />
          </linearGradient>
          <radialGradient id={ambient} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--brand-primary)" stopOpacity="0.18" />
            <stop offset="55%" stopColor="#7c3aed" stopOpacity="0.06" />
            <stop offset="100%" stopColor="var(--brand-primary)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Faint starfield — depth behind the whole system. */}
        {STARS.map((s, i) => (
          <circle
            key={`star-${i}`}
            cx={s.cx}
            cy={s.cy}
            r={s.r}
            fill="var(--foreground)"
            className="hv-star"
            style={{ animationDelay: `${s.delay}s` }}
          />
        ))}

        {/* A single restrained glow lifts the core off the background. */}
        <circle cx="500" cy="500" r="300" fill={`url(#${ambient})`} className="hv-core" />

        {/* Faint guide ring through the nodes — the ecosystem's structure. */}
        <circle
          cx="500"
          cy="500"
          r="360"
          stroke="var(--border)"
          strokeWidth="1"
          strokeOpacity="0.5"
          strokeDasharray="1 9"
          className="hv-orbit"
        />

        {/* Spokes — a faint base wire + a brighter dash that flows along it. */}
        {points.map((p) => (
          <line
            key={`w-${p.label}`}
            x1={p.x1}
            y1={p.y1}
            x2={p.x2}
            y2={p.y2}
            stroke={`url(#${link})`}
            strokeWidth="1.1"
            strokeOpacity="0.22"
            strokeLinecap="round"
          />
        ))}
        {points.map((p, i) => (
          <line
            key={`f-${p.label}`}
            x1={p.x1}
            y1={p.y1}
            x2={p.x2}
            y2={p.y2}
            stroke="var(--brand-secondary)"
            strokeWidth="1.5"
            strokeOpacity="0.6"
            strokeLinecap="round"
            strokeDasharray="2 14"
            className="hv-flow"
            style={{ animationDelay: `${(i * 0.2).toFixed(2)}s` }}
          />
        ))}

        {/* Discrete data packets travelling node → core: connections that ROUTE
            into the hub. One bright dot per spoke (round-capped), heavily
            staggered so it reads as occasional activity, never a marquee. */}
        {points.map((p, i) => (
          <line
            key={`pkt-${p.label}`}
            x1={p.x2}
            y1={p.y2}
            x2={p.x1}
            y2={p.y1}
            stroke="var(--brand-secondary)"
            strokeWidth="2.6"
            strokeLinecap="round"
            strokeDasharray="0.5 240"
            className="hv-packet"
            style={
              {
                "--len": SPOKE_LEN,
                animationDelay: `${(i * 0.34).toFixed(2)}s`,
              } as React.CSSProperties
            }
          />
        ))}

        {/* Pulsing connection ports where each wire meets the core ring. */}
        {points.map((p, i) => (
          <circle
            key={`port-${p.label}`}
            cx={p.x1}
            cy={p.y1}
            r="2.6"
            fill="var(--brand-secondary)"
            className="hv-twinkle"
            style={{ animationDelay: `${(i * 0.27).toFixed(2)}s` }}
          />
        ))}

        {/* Two accent rings hugging the hub, counter-rotating for quiet depth. */}
        <circle
          cx="500"
          cy="500"
          r="214"
          stroke="var(--brand-secondary)"
          strokeWidth="1"
          strokeOpacity="0.38"
          strokeDasharray="2 12"
          className="hv-spin"
        />
        <circle
          cx="500"
          cy="500"
          r="242"
          stroke="var(--brand-primary)"
          strokeWidth="1"
          strokeOpacity="0.18"
          strokeDasharray="1 13"
          className="hv-spin-rev"
        />
      </svg>

      {/* ── Core (HTML): premium glass hub + breathing glow + the X mark ── */}
      <div className="absolute left-1/2 top-1/2 aspect-square w-[45%] -translate-x-1/2 -translate-y-1/2">
        {/* Breathing outer glow — the core's gravitational presence. */}
        <div
          className="hv-ring absolute inset-[-22%] rounded-full"
          style={{
            background:
              "radial-gradient(circle, color-mix(in oklab, var(--brand-primary) 46%, transparent), transparent 70%)",
          }}
        />
        {/* Glass disc — material, depth, top-light reflection. */}
        <div
          className="relative grid h-full w-full place-items-center overflow-hidden rounded-full"
          style={{
            background:
              "radial-gradient(circle at 50% 36%, #16203a, #0a0f1e 60%, #070b16)",
            border: "1px solid color-mix(in oklab, var(--brand-primary) 44%, transparent)",
            boxShadow:
              "inset 0 1px 1px rgba(255,255,255,0.14), inset 0 -24px 48px rgba(0,0,0,0.55), 0 36px 84px -34px rgba(0,0,0,0.9)",
          }}
        >
          <div
            className="pointer-events-none absolute inset-0 rounded-full"
            style={{
              background:
                "linear-gradient(180deg, rgba(255,255,255,0.12), rgba(255,255,255,0) 44%)",
            }}
          />
          {/* A brand-light highlight that slowly travels the rim — the premium
              "light catching the edge" sheen on the glass hub. */}
          <div
            className="hv-spin pointer-events-none absolute inset-0 rounded-full"
            style={{
              background:
                "conic-gradient(from 0deg, transparent 285deg, color-mix(in oklab, var(--brand-secondary) 55%, transparent) 330deg, color-mix(in oklab, var(--brand-secondary) 95%, transparent) 348deg, transparent 360deg)",
              WebkitMaskImage:
                "radial-gradient(closest-side, transparent 90%, #000 92%)",
              maskImage:
                "radial-gradient(closest-side, transparent 90%, #000 92%)",
              opacity: 0.8,
            }}
          />
          <LogoMark
            animated
            className="relative h-[66%] w-[66%] drop-shadow-[0_12px_44px_rgba(56,128,255,0.6)]"
          />
        </div>
      </div>

      {/* ── Nodes (HTML): refined icon badges, evenly placed, gently floating ── */}
      {points.map((p, i) => {
        const Icon = p.Icon;
        return (
          <div
            key={`n-${p.label}`}
            className="absolute"
            style={{ left: `${p.left}%`, top: `${p.top}%`, transform: "translate(-50%, -50%)" }}
          >
            <div
              className="hv-drift flex flex-col items-center gap-2"
              style={{ animationDelay: `${(i * 0.55).toFixed(2)}s` }}
            >
              <span
                className="grid h-14 w-14 place-items-center rounded-full border border-border/70 backdrop-blur-md"
                style={BADGE_STYLE}
              >
                <Icon
                  className="h-[1.4rem] w-[1.4rem] text-foreground/85"
                  strokeWidth={1.6}
                />
              </span>
              <span className="font-display text-[13px] font-medium tracking-tight text-muted-foreground">
                {p.label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
