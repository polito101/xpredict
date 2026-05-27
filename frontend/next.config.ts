import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

const nextConfig: NextConfig = {
  /* defaults from scaffold; Phase 1 ships minimal config. */
};

export default withSentryConfig(nextConfig, {
  // Per 01-RESEARCH Pattern 5c — Phase 1 manual setup, no wizard.
  silent: !process.env.CI,
  org: "xpredict",
  project: "xpredict-dev",
  // Disable source-map upload entirely in Phase 1 (Phase 11 polish — D-29).
  // Without a SENTRY_AUTH_TOKEN, the plugin would no-op anyway; opt out explicitly
  // so dev/CI builds don't print spurious "skipping upload" warnings.
  sourcemaps: {
    disable: true,
  },
  // Don't auto-add /monitoring tunnel route in Phase 1; we'll revisit in Phase 11.
  tunnelRoute: undefined,
});
