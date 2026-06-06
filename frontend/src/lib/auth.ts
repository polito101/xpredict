/**
 * Plan 02-04 — Player auth Server Actions.
 *
 * Five Server Actions for the player surface:
 *   - loginAction               — OAuth2 form post to /auth/login (cookie session)
 *   - registerAction            — JSON post to /auth/register
 *   - forgotPasswordAction      — JSON post to /auth/forgot-password (enumeration-safe)
 *   - resetPasswordAction       — JSON post to /auth/reset-password
 *   - verifyEmailAction         — JSON post to /auth/verify (called from the page on mount)
 *
 * Schemas + types live in `./auth-schemas` because Next 15's `"use server"`
 * files may only export async functions.
 *
 * Trust boundaries (see <threat_model> in 02-04-PLAN.md):
 *   - Browser → Server Action: zod schemas are UX-only; the backend always re-validates.
 *   - Server Action → FastAPI: server-side fetch reads `BACKEND_URL` from process.env
 *     (no `NEXT_PUBLIC_` prefix — secrets do not leak into the client bundle).
 *
 * Cookie forwarding (Pitfall / RESEARCH §"Pattern 5" lines 862-876):
 *   FastAPI's /auth/login response carries `Set-Cookie: xpredict_session=...; HttpOnly;
 *   SameSite=Lax; Path=/; Max-Age=2592000`. The Server Action runtime cannot transparently
 *   relay a cookie set by a cross-origin response; instead, parse the Set-Cookie header
 *   and re-set it via `cookies().set(...)` so Next.js serializes it back to the browser.
 */
"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  LoginSchema,
  RegisterSchema,
  ForgotSchema,
  ResetSchema,
  VerifySchema,
  AdminLoginSchema,
  type ActionErrors,
  type ActionState,
  type VerifyResult,
} from "./auth-schemas";

// Schemas + types are re-exported through `./auth-schemas` — import them from
// there directly in client components.

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

function tooManyAttempts(): { errors: ActionErrors } {
  return {
    errors: { _form: ["Too many attempts. Try again in a minute."] },
  };
}

/**
 * Parse the first `xpredict_session=<value>` segment of a Set-Cookie header
 * and re-set it via `next/headers > cookies()` so the browser stores it.
 *
 * The FastAPI side already configures the canonical attributes (HttpOnly +
 * SameSite=Lax + Secure in prod + Max-Age). We mirror those here so the
 * Server Action's response to the browser carries the same shape — Next.js
 * does not transparently forward Set-Cookie across origins.
 */
async function forwardSessionCookie(
  setCookieHeader: string | null,
): Promise<void> {
  if (!setCookieHeader) return;
  const match = setCookieHeader.match(/(?:^|;\s*)xpredict_session=([^;]+)/);
  if (!match) return;
  const value = match[1];
  // Best-effort attribute parsing (Max-Age) — fall back to safe defaults.
  const maxAgeMatch = setCookieHeader.match(/Max-Age=(\d+)/i);
  const maxAge = maxAgeMatch ? Number(maxAgeMatch[1]) : 60 * 60 * 24 * 30;
  const store = await cookies();
  store.set("xpredict_session", value, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge,
  });
}

// ---------------------------------------------------------------------------
// loginAction (RESEARCH §"Pattern 5" lines 822-878 — canonical shape)
// ---------------------------------------------------------------------------

export async function loginAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const parsed = LoginSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) {
    return { errors: parsed.error.flatten().fieldErrors };
  }

  const res = await fetch(`${getBackendUrl()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      username: parsed.data.email,
      password: parsed.data.password,
    }),
    credentials: "include",
  });

  if (res.status === 429) return tooManyAttempts();
  if (!res.ok) {
    return { errors: { _form: ["Invalid credentials"] } };
  }

  await forwardSessionCookie(res.headers.get("set-cookie"));
  // Phase 19: land in the app (markets) after login; the public landing is `/`.
  redirect("/markets");
}

// ---------------------------------------------------------------------------
// logoutAction (v1.1 Fase C) — revoke server-side + clear the session cookie.
// ---------------------------------------------------------------------------

export async function logoutAction(): Promise<void> {
  const store = await cookies();
  const session = store.get("xpredict_session")?.value;
  // Best-effort revoke on the backend (fastapi-users cookie /auth/logout). If
  // it fails, the cookie is still cleared below, so the browser is logged out.
  if (session) {
    try {
      await fetch(`${getBackendUrl()}/auth/logout`, {
        method: "POST",
        headers: { cookie: `xpredict_session=${session}` },
      });
    } catch {
      // Network/endpoint hiccup — fall through to the local cookie clear.
    }
  }
  store.delete("xpredict_session");
  redirect("/");
}

// ---------------------------------------------------------------------------
// registerAction
// ---------------------------------------------------------------------------

export async function registerAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const display_nameRaw = formData.get("display_name");
  const parsed = RegisterSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    confirm_password: formData.get("confirm_password"),
    display_name:
      typeof display_nameRaw === "string" && display_nameRaw.trim().length > 0
        ? display_nameRaw
        : undefined,
  });
  if (!parsed.success) {
    return { errors: parsed.error.flatten().fieldErrors };
  }

  const res = await fetch(`${getBackendUrl()}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: parsed.data.email,
      password: parsed.data.password,
      display_name: parsed.data.display_name,
    }),
    credentials: "include",
  });

  if (res.status === 429) return tooManyAttempts();

  if (res.status === 400 || res.status === 422) {
    // fastapi-users surfaces `detail.reason` (or just `detail`) on conflict.
    let message = "Registration failed";
    try {
      const data = (await res.json()) as {
        detail?: unknown;
      };
      if (typeof data.detail === "string") {
        message = data.detail;
      } else if (
        typeof data.detail === "object" &&
        data.detail !== null &&
        "reason" in data.detail &&
        typeof (data.detail as { reason?: unknown }).reason === "string"
      ) {
        message = (data.detail as { reason: string }).reason;
      }
    } catch {
      // Body wasn't JSON — keep generic message.
    }
    return { errors: { _form: [message] } };
  }

  if (!res.ok) {
    return { errors: { _form: ["Registration failed. Please try again."] } };
  }

  redirect("/login?registered=1");
}

// ---------------------------------------------------------------------------
// forgotPasswordAction
// Always returns the SAME generic success message (T-02-38 mitigation).
// ---------------------------------------------------------------------------

export async function forgotPasswordAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const parsed = ForgotSchema.safeParse({ email: formData.get("email") });
  if (!parsed.success) {
    return { errors: parsed.error.flatten().fieldErrors };
  }

  // Fire-and-forget — the backend returns 202 either way. We deliberately
  // swallow non-2xx so the user sees the same generic message regardless
  // of email existence (enumeration mitigation, mirrors backend behaviour).
  try {
    await fetch(`${getBackendUrl()}/auth/forgot-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: parsed.data.email }),
    });
  } catch {
    // Network failure should still surface the same message to avoid leaking
    // whether the request reached the backend. Operator audit lives server-side.
  }

  return {
    success: true,
    message:
      "If an account with that email exists, you will receive a reset link.",
  };
}

// ---------------------------------------------------------------------------
// resetPasswordAction
// ---------------------------------------------------------------------------

export async function resetPasswordAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const parsed = ResetSchema.safeParse({
    token: formData.get("token"),
    password: formData.get("password"),
    confirm_password: formData.get("confirm_password"),
  });
  if (!parsed.success) {
    return { errors: parsed.error.flatten().fieldErrors };
  }

  const res = await fetch(`${getBackendUrl()}/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token: parsed.data.token,
      password: parsed.data.password,
    }),
  });

  if (res.status === 429) return tooManyAttempts();
  if (res.status === 400) {
    return { errors: { _form: ["Invalid or expired token"] } };
  }
  if (!res.ok) {
    return { errors: { _form: ["Password reset failed. Please try again."] } };
  }

  redirect("/login?reset=1");
}

// ---------------------------------------------------------------------------
// verifyEmailAction — called from the verify-email page on mount.
// Not a form action; returns a status object (not ActionState).
// ---------------------------------------------------------------------------

export async function verifyEmailAction(token: string): Promise<VerifyResult> {
  const parsed = VerifySchema.safeParse({ token });
  if (!parsed.success) {
    return { status: "error", detail: "Missing or invalid token" };
  }
  try {
    const res = await fetch(`${getBackendUrl()}/auth/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: parsed.data.token }),
    });
    if (!res.ok) {
      return { status: "error", detail: `Verification failed (${res.status})` };
    }
    return { status: "success" };
  } catch (e) {
    return {
      status: "error",
      detail: e instanceof Error ? e.message : "Verification failed",
    };
  }
}

// ---------------------------------------------------------------------------
// adminLoginAction (Plan 02-05 — AUTH-07, D-13)
// ---------------------------------------------------------------------------
//
// POSTs OAuth2 username/password to FastAPI's `/admin/auth/login` (shipped in
// Plan 02-03), parses the `{access_token, token_type}` JSON response, and
// stores the access_token in an HttpOnly `admin_jwt` cookie SCOPED TO `/admin/`
// so the admin Bearer NEVER leaks to player routes (T-02-50 — browser-side
// defense-in-depth). Mirrors the player `loginAction` shape with three key
// differences:
//
//   - Backend response is JSON (not Set-Cookie) — admin surface uses Bearer
//     transport (Plan 02-03 D-03); we manually re-wrap it as a cookie.
//   - Cookie `path: '/admin'` — browser only sends `admin_jwt` on /admin/*.
//   - `maxAge` matches backend's ACCESS_TOKEN_LIFETIME_SECONDS=900 (15 min).
//
// Trust boundary: T-02-55 — the access_token is set via cookies().set()
// server-side; the action's return value is `{success: true}` or an error
// object. The token NEVER leaves the server-side rendering boundary.
export async function adminLoginAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const parsed = AdminLoginSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) {
    return { errors: parsed.error.flatten().fieldErrors };
  }

  const res = await fetch(`${getBackendUrl()}/admin/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      username: parsed.data.email,
      password: parsed.data.password,
    }),
  });

  if (res.status === 429) return tooManyAttempts();
  if (!res.ok) {
    return { errors: { _form: ["Invalid credentials"] } };
  }

  let access_token: string | undefined;
  let token_type: string | undefined;
  try {
    const data = (await res.json()) as {
      access_token?: unknown;
      token_type?: unknown;
    };
    if (typeof data.access_token === "string") access_token = data.access_token;
    if (typeof data.token_type === "string") token_type = data.token_type;
  } catch {
    return {
      errors: { _form: ["Admin login failed: unexpected response shape"] },
    };
  }

  if (!access_token || token_type !== "bearer") {
    return {
      errors: { _form: ["Admin login failed: missing access_token"] },
    };
  }

  const store = await cookies();
  store.set("admin_jwt", access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/admin",
    maxAge: 900, // matches ACCESS_TOKEN_LIFETIME_SECONDS (Plan 02-01)
  });

  redirect("/admin");
}
