/** Single source of truth for site-level metadata and copy. */
export const siteConfig = {
  name: "XPredict",
  description:
    "A modern prediction market platform. Trade on real-world events across politics, sports, crypto, and culture — with play money.",
  url: "http://localhost:3000",
} as const;

export type SiteConfig = typeof siteConfig;
