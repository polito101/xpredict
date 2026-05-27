/**
 * Plan 02-05 Task 1 — Edge middleware tests.
 *
 * The Next.js Edge middleware at `frontend/src/middleware.ts` guards every
 * `/admin/*` route by verifying the `admin_jwt` HttpOnly cookie with
 * `jose.jwtVerify` against `ADMIN_JWT_PUBLIC_SECRET` (HS256 shared secret per
 * RESEARCH Assumption A8). This file asserts the SIX behaviours required by
 * the PLAN `<behavior>` block:
 *
 *   1. redirects_unauthenticated_admin_request — no cookie → 307 to /admin/login
 *   2. passes_through_admin_login_route       — even without a cookie, /admin/login renders
 *   3. passes_through_non_admin_routes        — /, /login, /api/healthz pass-through
 *   4. passes_through_valid_admin_jwt         — HS256-signed token with the right secret
 *   5. redirects_on_invalid_jwt_signature     — token signed with a different secret
 *   6. redirects_on_expired_jwt               — token whose `exp` is in the past
 *
 * Runs under the `node` environment (vitest.config.ts environmentMatchGlobs
 * picks `.test.ts` for node). Next.js's `next/server` shim works in node
 * because `NextRequest` / `NextResponse` are thin wrappers around the Web
 * Request / Response APIs which Node 20+ exposes natively.
 *
 * NOTE on the "OPTIMISTIC" middleware contract (RESEARCH lines 913-914): this
 * file ONLY verifies signature + expiry. The authoritative `is_superuser`
 * check happens server-side via FastAPI's `current_active_admin` dependency.
 * A forged-but-correctly-signed JWT would pass middleware here — that is by
 * design; the backend rejects it on the actual `/admin/*` API call.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { NextRequest } from "next/server";
import { SignJWT } from "jose";

import { middleware } from "../middleware";

const VALID_SECRET = "test-secret-32-chars-long-XXXX-AAAA";
const WRONG_SECRET = "different-secret-32-chars-long-BBBB";

async function makeAdminJwt(
  secret: string,
  options: { expiresIn?: string; expirationDate?: Date } = {},
): Promise<string> {
  const encodedSecret = new TextEncoder().encode(secret);
  const builder = new SignJWT({ sub: "admin-id-test", is_superuser: true })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt();
  if (options.expirationDate) {
    builder.setExpirationTime(Math.floor(options.expirationDate.getTime() / 1000));
  } else {
    builder.setExpirationTime(options.expiresIn ?? "15m");
  }
  return builder.sign(encodedSecret);
}

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

beforeEach(() => {
  vi.stubEnv("ADMIN_JWT_PUBLIC_SECRET", VALID_SECRET);
});

describe("middleware()", () => {
  it("redirects_unauthenticated_admin_request — no cookie → /admin/login", async () => {
    const req = buildRequest("/admin/users");
    const res = await middleware(req);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/admin/login");
  });

  it("passes_through_admin_login_route — /admin/login itself never redirects", async () => {
    const req = buildRequest("/admin/login");
    const res = await middleware(req);
    // NextResponse.next() returns 200 with no Location header.
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("passes_through_non_admin_routes — /, /login, /api/healthz", async () => {
    for (const path of ["/", "/login", "/api/healthz", "/register"]) {
      const req = buildRequest(path);
      const res = await middleware(req);
      expect(res.status).toBe(200);
      expect(res.headers.get("location")).toBeNull();
    }
  });

  it("passes_through_valid_admin_jwt — HS256-signed with the right secret", async () => {
    const token = await makeAdminJwt(VALID_SECRET, { expiresIn: "15m" });
    const req = buildRequest("/admin/users", { cookies: { admin_jwt: token } });
    const res = await middleware(req);
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("redirects_on_invalid_jwt_signature — token signed with a different secret", async () => {
    const token = await makeAdminJwt(WRONG_SECRET, { expiresIn: "15m" });
    const req = buildRequest("/admin/users", { cookies: { admin_jwt: token } });
    const res = await middleware(req);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/admin/login");
  });

  it("redirects_on_expired_jwt — exp in the past", async () => {
    const past = new Date(Date.now() - 60 * 1000); // 1 min ago
    const token = await makeAdminJwt(VALID_SECRET, { expirationDate: past });
    const req = buildRequest("/admin/users", { cookies: { admin_jwt: token } });
    const res = await middleware(req);
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toContain("/admin/login");
  });
});
