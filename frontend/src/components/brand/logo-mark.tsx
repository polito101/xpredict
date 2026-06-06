/**
 * LogoMark — the official XPrediction logo, used everywhere the product mark
 * appears (navbar default, hero, auth, admin).
 *
 * It shows the REAL raster asset committed at `public/brand/xprediction-logo.png`
 * (no reinterpretation, no recreation). Until that file exists it shows the
 * faithful vector mark (`XMark`) — and it does so WITHOUT ever flashing a broken
 * image: the SVG renders by default and the PNG is only swapped in once it
 * actually loads (`onLoad`). A 404 simply leaves the SVG in place. The moment the
 * official file is dropped at that path, every surface shows it automatically,
 * with no other change.
 *
 * (The white-label OPERATOR logo, when configured, still overrides this in the
 * navbar via `<img src=/branding/logo>` in `BrandLogo`.)
 *
 * Drop the official file at: frontend/public/brand/xprediction-logo.png
 */
"use client";

import { useState } from "react";

import { XMark } from "@/components/brand/x-mark";
import { cn } from "@/lib/utils";

/** Public path of the official asset (served from `frontend/public`). */
export const OFFICIAL_LOGO_SRC = "/brand/xprediction-logo.png";

export interface LogoMarkProps {
  className?: string;
  /** Animate the spark on the SVG mark (no-op for the raster asset). */
  animated?: boolean;
}

export function LogoMark({ className, animated }: LogoMarkProps) {
  const [loaded, setLoaded] = useState(false);

  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      {/* Default: the faithful vector mark (no network, never broken). */}
      {!loaded && <XMark animated={animated} className="h-full w-full" />}

      {/* The official asset, probed silently — only shown once it truly loads. */}
      {/* eslint-disable-next-line @next/next/no-img-element -- local brand asset
          with a graceful SVG fallback; next/image can't express "show the SVG
          until the official file is present". */}
      <img
        src={OFFICIAL_LOGO_SRC}
        alt=""
        aria-hidden="true"
        onLoad={() => setLoaded(true)}
        className={cn(
          "h-full w-full object-contain",
          !loaded && "pointer-events-none absolute inset-0 opacity-0",
        )}
      />
    </span>
  );
}
