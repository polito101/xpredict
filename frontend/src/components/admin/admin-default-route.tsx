/**
 * Plan 10-04 — AdminDefaultRoute: a tiny client component (mounted by the
 * /admin dashboard page) that records the dashboard as the admin landing
 * across sessions via a sessionStorage flag (SC#1 / D-11).
 *
 * SECURITY (T-10-14, RESEARCH §Security V3): this flag is a UX HINT ONLY. It is
 * WRITTEN here and NEVER READ by any auth or redirect path. The authoritative
 * landing is the EXISTING `adminLoginAction` → `redirect("/admin")` in
 * lib/auth.ts plus the Edge middleware Bearer verify — this component performs
 * no redirect and gates nothing.
 */
"use client";

import * as React from "react";

export function AdminDefaultRoute() {
  React.useEffect(() => {
    try {
      sessionStorage.setItem("admin_default_route", "/admin");
    } catch {
      // sessionStorage may be unavailable (private mode / SSR hydration race);
      // this is a pure UX hint, so a failure is silently ignored.
    }
  }, []);
  return null;
}
