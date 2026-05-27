/**
 * Plan 02-05 Task 1 — Edge middleware for /admin/* (AUTH-07, D-13).
 *
 * Optimistically gates the `/admin/*` route tree by verifying the
 * `admin_jwt` cookie with HS256 against `ADMIN_JWT_PUBLIC_SECRET`
 * (RESEARCH Assumption A8: HS256 shared secret in v1; Phase 11 will move
 * to RS256 with asymmetric keys). Verbatim from RESEARCH §"Pattern 5
 * admin middleware" lines 883-911.
 *
 * Trust boundary (PLAN <threat_model>):
 *   - This middleware is OPTIMISTIC — it stops anonymous browsers from
 *     reaching the admin shell. The AUTHORITATIVE gate is FastAPI's
 *     `current_active_admin` dependency on every `/admin/*` API call
 *     (RESEARCH §"Anti-Patterns" lines 913-914 + Plan 02-03 backend).
 *   - The middleware runs on the Edge runtime, which has NO database
 *     access. We MUST NOT add any DB lookup here (Anti-pattern
 *     RESEARCH line 923).
 *   - `process.env.ADMIN_JWT_PUBLIC_SECRET` MUST equal the backend's
 *     `SECRET_KEY` — otherwise every admin session will fail-closed
 *     here, but legitimate Bearer tokens minted by the backend will
 *     still be valid against `current_active_admin` (T-02-53).
 *
 * Verification is signature + expiry only — algorithm pinned to HS256
 * to defeat algorithm-confusion attacks (T-02-47, RESEARCH Pitfall
 * "Algorithm confusion": NEVER pass undefined algorithms to jwtVerify).
 */
import { NextRequest, NextResponse } from "next/server";

const ADMIN_PROTECTED = /^\/admin(\/|$)/;
const ADMIN_LOGIN = "/admin/login";

/**
 * Optimistic gate: redirects anonymous browsers away from the admin shell.
 * The backend uses DatabaseStrategy (opaque tokens), not JWT — so we only
 * check cookie presence here. The authoritative gate is FastAPI's
 * current_active_admin dependency on every /admin/* API call.
 */
export function proxy(req: NextRequest) {
  if (!ADMIN_PROTECTED.test(req.nextUrl.pathname)) return NextResponse.next();
  if (req.nextUrl.pathname === ADMIN_LOGIN) return NextResponse.next();

  const token = req.cookies.get("admin_jwt")?.value;
  if (!token) return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url));

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*"],
};
