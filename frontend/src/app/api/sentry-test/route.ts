// XPredict frontend Sentry triple-trigger endpoint (D-29).
//
// Phase 1 ships this naked — Phase 11 may gate it behind `?key=` or remove
// it entirely (CONTEXT D-29 + T-02-02). Hitting `GET /api/sentry-test`
// throws synchronously inside the Route Handler; Next.js converts it to a
// 500 and @sentry/nextjs (server SDK initialised in `instrumentation.ts`)
// captures the error tagged `service=frontend`.

export async function GET(): Promise<Response> {
  throw new Error("sentry test from frontend");
}
