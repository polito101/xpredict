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
import { jwtVerify } from "jose";

const ADMIN_PROTECTED = /^\/admin(\/|$)/;
const ADMIN_LOGIN = "/admin/login";

// Fail loudly at module load if the secret is absent — a missing secret means
// every admin JWT verification will fail-closed (redirect loop) with no
// visible error to operators.  Throwing here surfaces the misconfiguration
// immediately on cold-start rather than silently on every admin request.
const _rawSecret = process.env.ADMIN_JWT_PUBLIC_SECRET;
if (!_rawSecret) {
  throw new Error(
    "ADMIN_JWT_PUBLIC_SECRET is not set — admin middleware cannot function",
  );
}
const ADMIN_SECRET = new TextEncoder().encode(_rawSecret);

export async function middleware(req: NextRequest) {
  if (!ADMIN_PROTECTED.test(req.nextUrl.pathname)) return NextResponse.next();
  if (req.nextUrl.pathname === ADMIN_LOGIN) return NextResponse.next();

  const token = req.cookies.get("admin_jwt")?.value;
  if (!token) return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url));

  try {
    await jwtVerify(token, ADMIN_SECRET, { algorithms: ["HS256"] });
    return NextResponse.next();
  } catch (err) {
    // JWTExpired is normal (session timed out) — redirect silently.
    // Any other error (wrong secret, algorithm mismatch, invalid key) is
    // a misconfiguration signal that warrants a server-side log.
    if (!(err instanceof Error && err.name === "JWTExpired")) {
      console.warn(
        "[admin-middleware] jwt verification failed:",
        (err as Error).message,
      );
    }
    return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url));
  }
}

export const config = {
  matcher: ["/admin/:path*"],
};
