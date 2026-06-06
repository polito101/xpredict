/**
 * LogoMark — the official XPrediction logo asset, used everywhere the product
 * mark appears (navbar default, hero, auth, admin).
 *
 * It renders the REAL raster asset committed at `public/brand/xprediction-logo.png`
 * — no reinterpretation, no recreation. If that file is not present yet, it falls
 * back to the vector `XMark` so nothing is ever broken; the moment the official
 * file is dropped at that path, every surface shows it automatically with no other
 * change. (The white-label operator logo, when configured, still overrides this in
 * the navbar via `<img src=/branding/logo>` in `BrandLogo`.)
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
  /** Animate the spark on the SVG fallback (no-op for the raster asset). */
  animated?: boolean;
}

export function LogoMark({ className, animated }: LogoMarkProps) {
  const [failed, setFailed] = useState(false);

  // Until the official file exists, fall back to the faithful vector mark.
  if (failed) {
    return <XMark className={className} animated={animated} />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- a static local brand
    // asset with an on-error fallback to the SVG mark; next/image can't express
    // the graceful "use the SVG until the official file is dropped" fallback.
    <img
      src={OFFICIAL_LOGO_SRC}
      alt=""
      aria-hidden="true"
      onError={() => setFailed(true)}
      className={cn("object-contain", className)}
    />
  );
}
