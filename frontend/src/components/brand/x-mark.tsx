/**
 * XMark — the XPrediction "X" mark, as a high-fidelity scalable SVG.
 *
 * Two crossing beveled bars — a liquid-silver diagonal and an electric-blue
 * diagonal — with a brilliant central spark (a white-hot core + a horizontal
 * lens-flare beam + a 4-point star). This is the faithful vector rendition of the
 * official logo, used as the default mark (and the fallback inside `LogoMark`
 * until the official raster is dropped at `public/brand/xprediction-logo.png`).
 *
 * Client component so each instance gets collision-free gradient ids (`useId`);
 * it renders identically on the server and the client.
 */
"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

export interface XMarkProps {
  className?: string;
  /** Render the central spark / lens-flare (default true). */
  spark?: boolean;
  /** Gently animate the spark (respects reduced-motion via CSS). */
  animated?: boolean;
}

export function XMark({
  className,
  spark = true,
  animated = false,
}: XMarkProps) {
  const uid = useId().replace(/:/g, "");
  const silver = `silver-${uid}`;
  const silverEdge = `silverEdge-${uid}`;
  const blue = `blue-${uid}`;
  const blueEdge = `blueEdge-${uid}`;
  const glow = `glow-${uid}`;
  const flareH = `flareH-${uid}`;
  const flareV = `flareV-${uid}`;

  return (
    <svg
      viewBox="0 0 120 120"
      aria-hidden="true"
      className={cn("h-8 w-8", className)}
    >
      <defs>
        {/* Liquid-silver bar (TL → BR). */}
        <linearGradient id={silver} x1="14" y1="14" x2="106" y2="106" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.45" stopColor="#D2DAE8" />
          <stop offset="1" stopColor="#828FA8" />
        </linearGradient>
        {/* Electric-blue bar (TR → BL). */}
        <linearGradient id={blue} x1="106" y1="14" x2="14" y2="106" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8FBEFF" />
          <stop offset="0.45" stopColor="#2F6BFF" />
          <stop offset="1" stopColor="#102E86" />
        </linearGradient>
        {/* Bevel highlight stripes (top facet of each bar). */}
        <linearGradient id={silverEdge} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.95" />
          <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={blueEdge} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#CFE2FF" stopOpacity="0.9" />
          <stop offset="1" stopColor="#CFE2FF" stopOpacity="0" />
        </linearGradient>
        <radialGradient id={glow} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#EAF3FF" stopOpacity="1" />
          <stop offset="0.35" stopColor="#7FB6FF" stopOpacity="0.55" />
          <stop offset="1" stopColor="#7FB6FF" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={flareH} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#EAF3FF" stopOpacity="0" />
          <stop offset="0.5" stopColor="#FFFFFF" stopOpacity="1" />
          <stop offset="1" stopColor="#EAF3FF" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={flareV} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#CFE2FF" stopOpacity="0" />
          <stop offset="0.5" stopColor="#FFFFFF" stopOpacity="0.95" />
          <stop offset="1" stopColor="#CFE2FF" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Silver bar: top-left → bottom-right. */}
      <g transform="rotate(45 60 60)">
        <rect x="4" y="45" width="112" height="30" rx="13" fill={`url(#${silver})`} />
        <rect x="10" y="48" width="100" height="7" rx="3.5" fill={`url(#${silverEdge})`} />
      </g>
      {/* Blue bar: top-right → bottom-left (laid over). */}
      <g transform="rotate(-45 60 60)">
        <rect x="4" y="45" width="112" height="30" rx="13" fill={`url(#${blue})`} />
        <rect x="10" y="48" width="100" height="7" rx="3.5" fill={`url(#${blueEdge})`} />
      </g>

      {spark && (
        <g
          className={animated ? "animate-spark" : undefined}
          style={{ transformOrigin: "60px 60px" }}
        >
          <circle cx="60" cy="60" r="30" fill={`url(#${glow})`} />
          {/* Horizontal lens-flare beam (the logo's signature). */}
          <rect x="14" y="58.6" width="92" height="2.8" rx="1.4" fill={`url(#${flareH})`} />
          {/* Vertical beam (shorter). */}
          <rect x="58.7" y="34" width="2.6" height="52" rx="1.3" fill={`url(#${flareV})`} />
          {/* 4-point star core. */}
          <path
            d="M60 40 L63.5 56.5 L80 60 L63.5 63.5 L60 80 L56.5 63.5 L40 60 L56.5 56.5 Z"
            fill="#F6FAFF"
          />
          <circle cx="60" cy="60" r="3.2" fill="#FFFFFF" />
        </g>
      )}
    </svg>
  );
}
