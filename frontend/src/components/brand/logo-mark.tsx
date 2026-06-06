/**
 * LogoMark — the official XPrediction logo, used everywhere the product mark
 * appears (navbar, hero, auth, admin).
 *
 * It renders the official raster asset committed at
 * `public/brand/xprediction-logo.png`. A defensive fallback to the vector mark
 * (`XMark`) covers the unlikely case the file is ever missing — detected both via
 * `onError` and a mount-time `naturalWidth` check (an `onError` that fires before
 * hydration would otherwise be lost). With the asset present it shows immediately,
 * no flash.
 *
 * (The white-label OPERATOR logo, when configured, still overrides this in the
 * navbar via `<img src=/branding/logo>` in `BrandLogo`.)
 */
"use client";

import { useEffect, useRef, useState } from "react";

import { XMark } from "@/components/brand/x-mark";
import { cn } from "@/lib/utils";

/** Public path of the official asset (served from `frontend/public`). */
export const OFFICIAL_LOGO_SRC = "/brand/xprediction-logo.png";

export interface LogoMarkProps {
  className?: string;
  /** Animate the spark on the vector fallback (the raster has its own spark). */
  animated?: boolean;
}

export function LogoMark({ className, animated }: LogoMarkProps) {
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const img = ref.current;
    // A 404 that resolved before hydration leaves the img "complete" with no size.
    if (img && img.complete && img.naturalWidth === 0) setFailed(true);
  }, []);

  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      {failed ? (
        <XMark animated={animated} className="h-full w-full" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- a static local
        // brand asset with a defensive SVG fallback; next/image can't express the
        // "fall back to the vector mark if the file is missing" behavior.
        <img
          ref={ref}
          src={OFFICIAL_LOGO_SRC}
          alt=""
          aria-hidden="true"
          onError={() => setFailed(true)}
          className="h-full w-full object-contain"
        />
      )}
    </span>
  );
}
