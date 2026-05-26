// XPredict frontend — Next.js 15 browser Sentry init (Pattern 5c).
//
// Loaded by Next.js automatically on the client; no `register()` wrapper or
// runtime guard — client init is always desired. DSN comes from
// `NEXT_PUBLIC_SENTRY_DSN` so it's available in the browser bundle (treated
// as a public write-only token per T-02-01 / CONTEXT D-14).
//
// The `service=frontend` tag mirrors `instrumentation.ts` so server-side
// and browser-side events from this surface share a single filter in Sentry
// — addressing T-02-03 (untagged-events tampering mitigation).

import * as Sentry from "@sentry/nextjs";

// Guard against empty-string DSN — Sentry SDK 10.x treats "" differently
// from undefined and enters an error state when it can't parse the DSN.
// Mirrors the backend's `if not settings.SENTRY_DSN: return` guard (WR-04).
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
if (dsn) {
  Sentry.init({
    dsn,
    tracesSampleRate: 0.1,
    environment: process.env.NODE_ENV,
    initialScope: {
      tags: { service: "frontend" },
    },
  });
}
