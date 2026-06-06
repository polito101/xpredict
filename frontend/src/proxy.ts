/**
 * Edge middleware — optimistic auth gates (AUTH-07, D-13 + Phase 19 app gate).
 *
 * TWO route trees are gated here:
 *
 *  1. ADMIN (`/admin/*`) — redirected to `/admin/login` unless the `admin_jwt`
 *     cookie is present.
 *  2. PLAYER APP (`/markets`, `/events`, `/portfolio`, `/wallet`) — Phase 19
 *     moved the real app behind authentication (the public `/` is a brand
 *     landing). These routes redirect to `/login` unless the `xpredict_session`
 *     cookie is present. The PUBLIC surfaces — `/`, `/login`, `/register`, the
 *     other `(auth)` pages, `/api/*` — are NOT in the matcher and stay open.
 *
 * Trust boundary (PLAN <threat_model>):
 *   - This middleware is OPTIMISTIC — it only checks cookie PRESENCE (no DB, no
 *     verification; the Edge runtime has no DB access). The AUTHORITATIVE gates
 *     are the backend dependencies: `current_active_admin` on every `/admin/*`
 *     API call, and the self-scoped session cookie that every authenticated
 *     player read forwards server-side. A forged cookie passes this gate but
 *     fails at the backend, so no data leaks.
 */
import { NextRequest, NextResponse } from "next/server";

const ADMIN_PROTECTED = /^\/admin(\/|$)/;
const PLAYER_PROTECTED = /^\/(markets|events|portfolio|wallet)(\/|$)/;
const ADMIN_LOGIN = "/admin/login";
const PLAYER_LOGIN = "/login";

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Admin tree — gated by the admin_jwt cookie (path-scoped to /admin).
  if (ADMIN_PROTECTED.test(pathname)) {
    if (pathname === ADMIN_LOGIN) return NextResponse.next();
    const token = req.cookies.get("admin_jwt")?.value;
    if (!token) return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url));
    return NextResponse.next();
  }

  // Player app tree — gated by the xpredict_session cookie (the public landing
  // and the (auth) pages are not in the matcher, so they never reach here).
  if (PLAYER_PROTECTED.test(pathname)) {
    const session = req.cookies.get("xpredict_session")?.value;
    if (!session) {
      const url = new URL(PLAYER_LOGIN, req.url);
      url.searchParams.set("next", pathname);
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/admin/:path*",
    "/markets/:path*",
    "/events/:path*",
    "/portfolio/:path*",
    "/wallet/:path*",
  ],
};
