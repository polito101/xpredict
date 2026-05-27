// XPredict frontend — Next.js 15 server-side Sentry init (Pattern 5c).
//
// Per @sentry/nextjs convention, this file's `register()` hook runs once
// when the Next.js Node runtime boots; we guard on `NEXT_RUNTIME === "nodejs"`
// so the edge runtime (which doesn't yet need Sentry coverage in Phase 1)
// is skipped. The exported `onRequestError = Sentry.captureRequestError`
// is the Next.js 15 server-error capture hook (requires @sentry/nextjs >=
// 8.28 per RESEARCH Assumption A4; we ship 10.x which satisfies this).
//
// `initialScope.tags.service = "frontend"` mirrors the backend's tag shape
// from Plan 01-01's `init_sentry()` helper — every Sentry event from any of
// the 4 surfaces (api / worker / beat / frontend) carries a `service` tag so
// alerts can be filtered per CONTEXT D-27.

import * as Sentry from "@sentry/nextjs";

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
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
  }
}

export const onRequestError = Sentry.captureRequestError;
