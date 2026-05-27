// XPredict frontend liveness endpoint.
//
// docker-compose's `frontend` service (Plan 01-03) curls this every 10s
// (per CONTEXT D-03). The body is `{"status":"ok"}` — no DB, no fetch, no
// async I/O — per threat T-02-04 (mitigate DoS via trivial work).

export async function GET(): Promise<Response> {
  return Response.json({ status: "ok" }, { status: 200 });
}
