/**
 * XMark — the official XPredict "X" mark, rebuilt as a crisp, scalable SVG.
 *
 * Two crossing beveled bars — one liquid-silver, one electric royal blue — with
 * a bright 4-point spark (lens-flare) at the crossing center. This is the brand's
 * signature: the instant where opinions cross and a prediction is made. It is the
 * DEFAULT logo mark, used by `BrandLogo` when no operator logo is configured; an
 * operator-uploaded logo still overrides it via `<img src=/branding/logo>`.
 *
 * Client component only so each instance gets collision-free gradient ids
 * (`useId`) — it renders identically on the server and the client.
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
  const blue = `blue-${uid}`;
  const glow = `glow-${uid}`;

  return (
    <svg
      viewBox="0 0 120 120"
      aria-hidden="true"
      className={cn("h-8 w-8", className)}
    >
      <defs>
        <linearGradient id={silver} x1="18" y1="18" x2="102" y2="102" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#FBFCFF" />
          <stop offset="0.5" stopColor="#CBD4E6" />
          <stop offset="1" stopColor="#7E8AA6" />
        </linearGradient>
        <linearGradient id={blue} x1="102" y1="18" x2="18" y2="102" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#7FB0FF" />
          <stop offset="0.5" stopColor="#2F6BFF" />
          <stop offset="1" stopColor="#173B9E" />
        </linearGradient>
        <radialGradient id={glow} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#EAF2FF" stopOpacity="0.95" />
          <stop offset="0.4" stopColor="#7FB0FF" stopOpacity="0.55" />
          <stop offset="1" stopColor="#7FB0FF" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Silver bar: top-left → bottom-right. */}
      <rect
        x="4"
        y="45"
        width="112"
        height="30"
        rx="13"
        fill={`url(#${silver})`}
        transform="rotate(45 60 60)"
      />
      {/* Blue bar: top-right → bottom-left (laid over). */}
      <rect
        x="4"
        y="45"
        width="112"
        height="30"
        rx="13"
        fill={`url(#${blue})`}
        transform="rotate(-45 60 60)"
      />

      {spark && (
        <g
          className={animated ? "animate-spark" : undefined}
          style={{ transformOrigin: "60px 60px" }}
        >
          <circle cx="60" cy="60" r="26" fill={`url(#${glow})`} />
          {/* 4-point star core. */}
          <path
            d="M60 36 L64.5 55.5 L84 60 L64.5 64.5 L60 84 L55.5 64.5 L36 60 L55.5 55.5 Z"
            fill="#F4F9FF"
          />
          <circle cx="60" cy="60" r="3.4" fill="#FFFFFF" />
        </g>
      )}
    </svg>
  );
}
