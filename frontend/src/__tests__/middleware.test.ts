/**
 * Plan 02-05 Task 1 — Edge proxy tests.
 *
 * The Next.js Edge proxy at `frontend/src/proxy.ts` optimistically gates
 * every `/admin/*` route by checking for the presence of the `admin_jwt`
 * HttpOnly cookie. JWT signature/expiry verification was removed; the
 * authoritative gate is FastAPI's `current_active_admin` dependency on
 * every `/admin/*` API call (RESEARCH §"Anti-Patterns" + Plan 02-03).
 *
 * Behaviours asserted:
 *   1. redirects_unauthenticated_admin_request — no cookie → 307 to /admin/login
 *   2. passes_through_admin_login_route        — /admin/login passes even without a cookie
 *   3. passes_through_non_admin_routes         — /, /login, /api/healthz pass through
 *   4. passes_through_admin_route_with_cookie  — any admin_jwt cookie value is accepted
 */
import { describe, it, expect } from "vitest";
import { NextRequest } from "next/server";

import { proxy } from "../proxy";

function buildRequest(
  path: string,
  opts: { cookies?: Record<string, string> } = {},
): NextRequest {
  const url = `http://localhost:3000${path}`;
  const headers = new Headers();
  if (opts.cookies && Object.keys(opts.cookies).length > 0) {
    const cookieHeader = Object.entries(opts.cookies)
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");
    headers.set("cookie", cookieHeader);
  }
  return new NextRequest(url, { headers });
}

describe("proxy()", () => {
  it("redirects_unauthenticated_admin_request — no cookie → /admin/login", () => {
    const req = buildRequest("/admin/users");
    const res = proxy(req);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/admin/login");
  });

  it("passes_through_admin_login_route — /admin/login itself never redirects", () => {
    const req = buildRequest("/admin/login");
    const res = proxy(req);
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("passes_through_non_admin_routes — /, /login, /api/healthz", () => {
    for (const path of ["/", "/login", "/api/healthz", "/register"]) {
      const req = buildRequest(path);
      const res = proxy(req);
      expect(res.status).toBe(200);
      expect(res.headers.get("location")).toBeNull();
    }
  });

  it("passes_through_admin_route_with_cookie — any admin_jwt cookie value is accepted", () => {
    const req = buildRequest("/admin/users", { cookies: { admin_jwt: "any-token-value" } });
    const res = proxy(req);
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });
});
