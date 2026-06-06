/**
 * Spark — the standalone 4-point lens-flare from the logo crossing.
 *
 * The brand's recurring "moment" element: hero crossings, a placed bet, a win.
 * Decorative only (`aria-hidden`). Animation respects reduced-motion via the
 * `animate-spark` utility (disabled under `prefers-reduced-motion`).
 */
"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

export interface SparkProps {
  className?: string;
  animated?: boolean;
}

export function Spark({ className, animated = true }: SparkProps) {
  const uid = useId().replace(/:/g, "");
  const core = `spark-core-${uid}`;

  return (
    <svg
      viewBox="0 0 64 64"
      aria-hidden="true"
      className={cn("h-6 w-6", animated && "animate-spark", className)}
      style={{ transformOrigin: "32px 32px" }}
    >
      <defs>
        <radialGradient id={core} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="0.35" stopColor="#BBD4FF" stopOpacity="0.9" />
          <stop offset="1" stopColor="#3B82F6" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="32" cy="32" r="18" fill={`url(#${core})`} />
      <path
        d="M32 6 L35 29 L58 32 L35 35 L32 58 L29 35 L6 32 L29 29 Z"
        fill="#EAF2FF"
      />
      <circle cx="32" cy="32" r="2.4" fill="#FFFFFF" />
    </svg>
  );
}
