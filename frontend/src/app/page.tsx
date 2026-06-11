/**
 * Landing — the public XPredict homepage: a single-viewport interactive hero.
 *
 * Visual-first sales-demo face (see docs/superpowers/specs/
 * 2026-06-11-home-x-grid-hero-design.md): one screen, the XParticles canvas,
 * minimal copy, two CTAs. The only backend read is the public branding (best-
 * effort — the landing renders with defaults even if the backend is down).
 */
import { XGridHero } from "@/components/home/x-grid-hero";
import { fetchBrandingPublic, DEFAULT_BRANDING } from "@/lib/branding-public";

export default async function Landing() {
  let brandName = DEFAULT_BRANDING.brand_name;
  try {
    brandName = (await fetchBrandingPublic()).brand_name;
  } catch {
    // Backend unreachable — keep the default brand; the landing must render.
  }
  return <XGridHero brandName={brandName} />;
}
