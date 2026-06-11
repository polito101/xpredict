/**
 * Landing — the public XPredict homepage: a single-viewport interactive hero.
 *
 * Visual-first sales-demo face (see docs/superpowers/specs/
 * 2026-06-11-home-x-grid-hero-design.md): exactly one screen, the XParticles
 * canvas, one headline, the CTAs — no backend reads at all. The demo gate
 * mirrors the login page: NEXT_PUBLIC_DEMO_MODE is resolved HERE (server)
 * so the one-click demo button is absent from white-label builds.
 */
import { XGridHero } from "@/components/home/x-grid-hero";

export default function Landing() {
  return <XGridHero demoMode={process.env.NEXT_PUBLIC_DEMO_MODE === "true"} />;
}
