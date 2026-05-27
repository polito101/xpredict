// XPredict frontend Sentry triple-trigger endpoint (D-29).
//
// Phase 1 ships this naked — Phase 11 may gate it behind `?key=` or remove
// it entirely (CONTEXT D-29 + T-02-02). Hitting `GET /api/sentry-test`
// throws synchronously inside the Route Handler; Sentry SDK captures the
// error tagged `service=frontend` via explicit captureException + flush
// (the `onRequestError` hook in instrumentation.ts only fires for
// rendering errors in Next.js 15, not for Route Handler exceptions).

import * as Sentry from "@sentry/nextjs";

export async function GET(): Promise<Response> {
  try {
    throw new Error("sentry test from frontend");
  } catch (err) {
    Sentry.captureException(err);
    await Sentry.flush(2000);
    throw err;
  }
}
