/**
 * Landing — the public XPredict brand homepage (Phase 19 positioning).
 *
 * XPredict is presented platform-first: a white-label, API-first engine for
 * prediction markets that teams use to RUN native markets, INTEGRATE external
 * ones, and LAUNCH their own. The live app (markets/portfolio/wallet) lives
 * behind authentication and is showcased here as the platform's live demo.
 *
 * Public + resilient: every backend read is best-effort (Promise.allSettled) and
 * degrades gracefully, so the landing renders even if the backend is unreachable.
 * Platform stats + featured cards are derived from the PUBLIC `/catalog` —
 * real backend data, no new API. The hero uses the runtime brand name.
 */
import { HeroBand } from "@/components/home/hero-band";
import { Pillars } from "@/components/home/pillars";
import { CapabilityGrid } from "@/components/home/capability-grid";
import { ApiSection } from "@/components/home/api-section";
import {
  DemoShowcase,
  type DemoStat,
} from "@/components/home/demo-showcase";
import { HowItWorks } from "@/components/home/how-it-works";
import { LandingCta } from "@/components/home/landing-cta";
import { fetchBrandingPublic, DEFAULT_BRANDING } from "@/lib/branding-public";
import { fetchCatalog, fetchCategories, type CatalogItem } from "@/lib/catalog";
import { formatVolume } from "@/lib/api";

export default async function Landing() {
  const [brandingResult, catalogResult, categoriesResult] =
    await Promise.allSettled([
      fetchBrandingPublic(),
      fetchCatalog({ sort: "volume" }),
      fetchCategories(),
    ]);

  const brandName =
    brandingResult.status === "fulfilled"
      ? brandingResult.value.brand_name
      : DEFAULT_BRANDING.brand_name;

  const catalog: CatalogItem[] =
    catalogResult.status === "fulfilled" ? catalogResult.value : [];
  const categories =
    categoriesResult.status === "fulfilled" ? categoriesResult.value : [];

  const featured = catalog.slice(0, 6);

  const stats: DemoStat[] = [];
  if (catalog.length > 0) {
    const events = catalog.filter((i) => i.type === "event").length;
    const totalVolume = catalog.reduce(
      (sum, i) => sum + (Number.parseFloat(i.volume) || 0),
      0,
    );
    stats.push(
      { label: "Markets", value: String(catalog.length) },
      { label: "Multi-outcome events", value: String(events) },
      { label: "Total volume", value: formatVolume(String(totalVolume)) },
    );
  }
  if (categories.length > 0) {
    stats.push({ label: "Categories", value: String(categories.length) });
  }

  return (
    <>
      <HeroBand brandName={brandName} />
      <Pillars />
      <CapabilityGrid />
      <ApiSection />
      <DemoShowcase featured={featured} stats={stats} />
      <HowItWorks />
      <LandingCta />
    </>
  );
}
