/**
 * HeroVisual — the XPrediction ecosystem node (Phase 19, evolved).
 *
 * The landing's signature, most-memorable piece: the "X" core rendered as a
 * LIVING network hub. From the core, connections emerge to the whole ecosystem
 * — users, platforms, APIs, house & external markets, data, liquidity,
 * integrations, communities, partners — with animated flow along the links,
 * slowly-rotating orbit rings, luminous nodes, layered depth and a violet→blue→
 * cyan glow. The message reads instantly: everything connects through XPrediction.
 *
 * Decorative (`aria-hidden`) — the hero's meaning lives in its text. All motion
 * is reduced-motion-safe (the `hv-*` classes are disabled under
 * `prefers-reduced-motion`). Client Component (collision-free `useId`).
 */
"use client";

import { useId } from "react";

import { LogoMark } from "@/components/brand/logo-mark";

const CX = 360;
const CY = 360;

type Node = { label: string; angle: number; r: number };

// The ecosystem the X connects. Long labels sit top/bottom (centered) where they
// have room; the rest fan out on an inner + outer ring.
const NODES: Node[] = [
  { label: "Users", angle: 90, r: 168 },
  { label: "Platforms", angle: 130, r: 262 },
  { label: "Communities", angle: 168, r: 170 },
  { label: "APIs", angle: 210, r: 262 },
  { label: "Data", angle: 250, r: 170 },
  { label: "Liquidity", angle: 290, r: 262 },
  { label: "Integrations", angle: 328, r: 176 },
  { label: "Partners", angle: 8, r: 262 },
  { label: "House markets", angle: 48, r: 196 },
  { label: "External markets", angle: 270, r: 264 },
];

function pos(angle: number, r: number) {
  const a = (angle * Math.PI) / 180;
  return { x: CX + r * Math.cos(a), y: CY - r * Math.sin(a) };
}

export function HeroVisual() {
  const uid = useId().replace(/:/g, "");
  const line = `hv-line-${uid}`;
  const nodeGlow = `hv-node-${uid}`;
  const coreGlow = `hv-core-${uid}`;
  const auroraA = `hv-aa-${uid}`;
  const auroraB = `hv-ab-${uid}`;

  const points = NODES.map((n) => ({ ...n, ...pos(n.angle, n.r) }));

  return (
    <div
      aria-hidden="true"
      className="relative mx-auto hidden aspect-square w-full max-w-[34rem] lg:block"
    >
      <svg
        viewBox="0 0 720 720"
        className="h-full w-full overflow-visible"
        fill="none"
      >
        <defs>
          <radialGradient id={auroraA} cx="50%" cy="42%" r="55%">
            <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.45" />
            <stop offset="55%" stopColor="var(--brand-primary)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--brand-primary)" stopOpacity="0" />
          </radialGradient>
          <radialGradient id={auroraB} cx="60%" cy="60%" r="50%">
            <stop offset="0%" stopColor="var(--brand-secondary)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--brand-secondary)" stopOpacity="0" />
          </radialGradient>
          <linearGradient id={line} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--brand-secondary)" />
            <stop offset="50%" stopColor="var(--brand-primary)" />
            <stop offset="100%" stopColor="#7c3aed" />
          </linearGradient>
          <radialGradient id={nodeGlow} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--brand-secondary)" stopOpacity="0.9" />
            <stop offset="100%" stopColor="var(--brand-secondary)" stopOpacity="0" />
          </radialGradient>
          <radialGradient id={coreGlow} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#bcd4ff" stopOpacity="0.85" />
            <stop offset="35%" stopColor="var(--brand-primary)" stopOpacity="0.5" />
            <stop offset="100%" stopColor="var(--brand-primary)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Depth: layered aurora glows. */}
        <circle cx="360" cy="320" r="320" fill={`url(#${auroraA})`} />
        <circle cx="430" cy="440" r="240" fill={`url(#${auroraB})`} />

        {/* Orbit rings — slow counter-rotating layers for a sense of a live sphere. */}
        <g className="hv-orbit" opacity="0.5">
          <circle
            cx={CX}
            cy={CY}
            r="170"
            stroke="var(--border-strong)"
            strokeWidth="1"
            strokeDasharray="2 10"
          />
          <circle
            cx={CX}
            cy={CY}
            r="262"
            stroke="var(--border)"
            strokeWidth="1"
            strokeDasharray="2 12"
          />
        </g>
        <g className="hv-orbit-rev" opacity="0.35">
          <circle
            cx={CX}
            cy={CY}
            r="216"
            stroke="var(--border-strong)"
            strokeWidth="1"
            strokeDasharray="1 14"
          />
        </g>

        {/* Connection lines — data flowing from the core to every node. */}
        <g>
          {points.map((p) => (
            <line
              key={`l-${p.label}`}
              x1={CX}
              y1={CY}
              x2={p.x}
              y2={p.y}
              stroke={`url(#${line})`}
              strokeWidth="1.4"
              strokeOpacity="0.55"
              strokeDasharray="2 8"
              strokeLinecap="round"
              className="hv-flow"
            />
          ))}
        </g>

        {/* Nodes — luminous dots + labels. */}
        {points.map((p) => {
          const cos = Math.cos((p.angle * Math.PI) / 180);
          const sin = Math.sin((p.angle * Math.PI) / 180);
          const anchor =
            cos > 0.25 ? "start" : cos < -0.25 ? "end" : "middle";
          const dx = anchor === "start" ? 14 : anchor === "end" ? -14 : 0;
          const dy = anchor === "middle" ? (sin > 0 ? -16 : 24) : 5;
          return (
            <g key={`n-${p.label}`}>
              <circle
                cx={p.x}
                cy={p.y}
                r="16"
                fill={`url(#${nodeGlow})`}
                className="hv-pulse"
              />
              <circle cx={p.x} cy={p.y} r="3.6" fill="#dbe7ff" />
              <circle
                cx={p.x}
                cy={p.y}
                r="6.5"
                fill="none"
                stroke="var(--brand-secondary)"
                strokeWidth="1"
                strokeOpacity="0.5"
              />
              <text
                x={p.x + dx}
                y={p.y + dy}
                textAnchor={anchor}
                className="font-display"
                fontSize="15"
                fontWeight="500"
                fill="var(--muted-foreground)"
              >
                {p.label}
              </text>
            </g>
          );
        })}

        {/* Core: glow + glass hub. The X mark sits on top via foreignObject. */}
        <circle
          cx={CX}
          cy={CY}
          r="120"
          fill={`url(#${coreGlow})`}
          className="hv-core"
        />
        <circle
          cx={CX}
          cy={CY}
          r="66"
          fill="color-mix(in oklab, var(--card) 70%, transparent)"
          stroke="color-mix(in oklab, var(--brand-primary) 45%, transparent)"
          strokeWidth="1.5"
        />
        <foreignObject x={CX - 52} y={CY - 52} width="104" height="104">
          <div className="flex h-full w-full items-center justify-center">
            <LogoMark animated className="h-[5.5rem] w-[5.5rem]" />
          </div>
        </foreignObject>
      </svg>
    </div>
  );
}
