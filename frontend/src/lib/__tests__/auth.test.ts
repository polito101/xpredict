/**
 * Plan 02-04 Task 1 — Server Actions tests (RED → GREEN).
 *
 * Validates `frontend/src/lib/auth.ts`:
 *   1. loginAction calls backend with OAuth2 form encoding + credentials:'include'.
 *   2. loginAction returns zod errors on invalid input WITHOUT calling fetch.
 *   3. loginAction redirects to '/' on 200.
 *   4. loginAction returns {_form: ['Invalid credentials']} on 401.
 *   5. RegisterSchema rejects weak passwords client-side (UX mirror, backend re-validates).
 *
 * Mocks:
 *   - `next/navigation` -> `redirect` is a spy that throws (mirrors Next behaviour).
 *   - `next/headers` -> `cookies()` returns a fake store.
 *   - global `fetch`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// --- Mocks: vi.mock is hoisted, so the factories cannot reference
//     module-scope variables. We use vi.hoisted() to expose the spies
//     to both the factory and the tests below.
// ---------------------------------------------------------------------

const mocks = vi.hoisted(() => {
  const redirectMock = vi.fn((url: string) => {
    // Real Next.js `redirect()` throws a NEXT_REDIRECT internal sentinel — we
    // simulate that with a tagged error so callers stop executing.
    const err = new Error(`NEXT_REDIRECT:${url}`);
    // @ts-expect-error: test sentinel
    err.digest = `NEXT_REDIRECT;replace;${url};303`;
    throw err;
  });
  const cookieStore = {
    set: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
  };
  const cookiesMock = vi.fn(async () => cookieStore);
  return { redirectMock, cookieStore, cookiesMock };
});

vi.mock("next/navigation", () => ({
  redirect: mocks.redirectMock,
}));

vi.mock("next/headers", () => ({
  cookies: mocks.cookiesMock,
}));

// --- SUT ---------------------------------------------------------------

import {
  loginAction,
  registerAction,
  forgotPasswordAction,
  resetPasswordAction,
  verifyEmailAction,
} from "../auth";
import { LoginSchema, RegisterSchema, type ActionState } from "../auth-schemas";

const { redirectMock, cookieStore } = mocks;

// Type narrowers used in the assertions below.
function asErrors(state: ActionState): {
  errors: Record<string, string[] | undefined>;
} {
  if (!state || !("errors" in state)) {
    throw new Error(`Expected action state with errors, got: ${JSON.stringify(state)}`);
  }
  return state;
}
function asSuccess(state: ActionState): { success: true; message: string } {
  if (!state || !("success" in state)) {
    throw new Error(`Expected success state, got: ${JSON.stringify(state)}`);
  }
  return state;
}

// Helpers ----------------------------------------------------------------

function fd(fields: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.append(k, v);
  return f;
}

// Spy on global fetch (different impl per test). Use a generic `unknown`-keyed
// mock rather than the narrow `ReturnType<typeof vi.spyOn<...>>` overload —
// `globalThis.fetch` is declared as a Web-API + Node.js intersection that the
// TS compiler refuses to feed into the constrained overload, and next-lint's
// `@typescript-eslint/no-explicit-any` blocks plain `any` at build time.
type FetchMock = {
  mockResolvedValue: (v: Response) => void;
  mockResolvedValueOnce: (v: Response) => void;
  mock: { calls: unknown[][] };
};
let fetchSpy: FetchMock;

beforeEach(() => {
  vi.clearAllMocks();
  redirectMock.mockClear();
  cookieStore.set.mockClear();
  // Default fetch — tests override per-case.
  fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(null, { status: 200 })) as unknown as FetchMock;
  process.env.BACKEND_URL = "http://backend.test";
});

// =========================================================================
// loginAction
// =========================================================================

describe("loginAction", () => {
  it("calls backend with OAuth2 form encoding + credentials:'include' on valid input", async () => {
    // The action throws NEXT_REDIRECT on success — catch to inspect calls.
    await expect(
      loginAction(undefined, fd({ email: "a@b.co", password: "valid-pass-12" })),
    ).rejects.toThrow(/NEXT_REDIRECT/);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [
      string,
      RequestInit | undefined,
    ];
    expect(url).toBe("http://backend.test/auth/login");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");

    // OAuth2 form body — must contain url-encoded username + password.
    const body = init?.body as URLSearchParams;
    expect(body).toBeInstanceOf(URLSearchParams);
    expect(body.get("username")).toBe("a@b.co");
    expect(body.get("password")).toBe("valid-pass-12");

    expect(init?.headers).toMatchObject({
      "Content-Type": "application/x-www-form-urlencoded",
    });
  });

  it("returns zod errors on invalid email WITHOUT calling fetch", async () => {
    const result = await loginAction(
      undefined,
      fd({ email: "not-an-email", password: "" }),
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result).toBeDefined();
    const errored = asErrors(result);
    // zod field errors arrive as arrays.
    expect(errored.errors.email).toBeTruthy();
  });

  it("redirects to '/' on backend 200", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 200 }));
    await expect(
      loginAction(undefined, fd({ email: "a@b.co", password: "x" })),
    ).rejects.toThrow(/NEXT_REDIRECT:\//);
    expect(redirectMock).toHaveBeenCalledWith("/");
  });

  it("returns {errors:{_form:['Invalid credentials']}} on 401", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 401 }));
    const result = await loginAction(
      undefined,
      fd({ email: "a@b.co", password: "x" }),
    );
    expect(redirectMock).not.toHaveBeenCalled();
    expect(asErrors(result).errors._form).toEqual(["Invalid credentials"]);
  });

  it("returns 'Too many attempts' on 429", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 429 }));
    const result = await loginAction(
      undefined,
      fd({ email: "a@b.co", password: "x" }),
    );
    expect(asErrors(result).errors._form?.[0]).toMatch(/too many/i);
  });

  it("forwards Set-Cookie xpredict_session from backend response to next/headers cookies", async () => {
    const headers = new Headers();
    headers.set(
      "set-cookie",
      "xpredict_session=abc123; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000",
    );
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 200, headers }));

    await expect(
      loginAction(undefined, fd({ email: "a@b.co", password: "x" })),
    ).rejects.toThrow(/NEXT_REDIRECT/);

    expect(cookieStore.set).toHaveBeenCalledTimes(1);
    const [name, value, opts] = cookieStore.set.mock.calls[0]!;
    expect(name).toBe("xpredict_session");
    expect(value).toBe("abc123");
    expect(opts).toMatchObject({ httpOnly: true, sameSite: "lax", path: "/" });
  });
});

// =========================================================================
// registerAction
// =========================================================================

describe("registerAction", () => {
  it("rejects passwords shorter than 12 chars without calling fetch", async () => {
    const result = await registerAction(
      undefined,
      fd({
        email: "a@b.co",
        password: "short",
        confirm_password: "short",
        display_name: "",
      }),
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(asErrors(result).errors.password).toBeTruthy();
  });

  it("rejects when password and confirm_password mismatch", async () => {
    const result = await registerAction(
      undefined,
      fd({
        email: "a@b.co",
        password: "Valid-Pass-1234",
        confirm_password: "Different-1234",
      }),
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(asErrors(result).errors.confirm_password).toBeTruthy();
  });

  it("posts JSON to /auth/register on valid input and redirects on 201", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 201 }));
    await expect(
      registerAction(
        undefined,
        fd({
          email: "a@b.co",
          password: "Valid-Pass-1234",
          confirm_password: "Valid-Pass-1234",
          display_name: "Alice",
        }),
      ),
    ).rejects.toThrow(/NEXT_REDIRECT:\/login\?registered=1/);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [
      string,
      RequestInit | undefined,
    ];
    expect(url).toBe("http://backend.test/auth/register");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
    expect(init?.headers).toMatchObject({ "Content-Type": "application/json" });
    const body = JSON.parse(init?.body as string);
    expect(body.email).toBe("a@b.co");
    expect(body.password).toBe("Valid-Pass-1234");
  });
});

// =========================================================================
// forgotPasswordAction (enumeration mitigation)
// =========================================================================

describe("forgotPasswordAction", () => {
  it("always returns the same generic success message regardless of backend response (200)", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 202 }));
    const result = await forgotPasswordAction(
      undefined,
      fd({ email: "user@example.com" }),
    );
    const ok = asSuccess(result);
    expect(ok.success).toBe(true);
    expect(ok.message).toMatch(/if an account/i);
  });

  it("returns the same generic message on backend 400 (unknown email)", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 400 }));
    const result = await forgotPasswordAction(
      undefined,
      fd({ email: "unknown@example.com" }),
    );
    const ok = asSuccess(result);
    expect(ok.success).toBe(true);
    expect(ok.message).toMatch(/if an account/i);
  });
});

// =========================================================================
// resetPasswordAction
// =========================================================================

describe("resetPasswordAction", () => {
  it("redirects to /login?reset=1 on backend 200", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 200 }));
    await expect(
      resetPasswordAction(
        undefined,
        fd({
          token: "xyz",
          password: "Valid-Pass-1234",
          confirm_password: "Valid-Pass-1234",
        }),
      ),
    ).rejects.toThrow(/NEXT_REDIRECT:\/login\?reset=1/);
  });

  it("returns Invalid-or-expired-token error on backend 400", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 400 }));
    const result = await resetPasswordAction(
      undefined,
      fd({
        token: "bad",
        password: "Valid-Pass-1234",
        confirm_password: "Valid-Pass-1234",
      }),
    );
    expect(asErrors(result).errors._form?.[0]).toMatch(/invalid or expired/i);
  });
});

// =========================================================================
// verifyEmailAction
// =========================================================================

describe("verifyEmailAction", () => {
  it("returns {status:'success'} when backend returns 200", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 200 }));
    const result = await verifyEmailAction("token-abc");
    expect(result.status).toBe("success");
  });

  it("returns {status:'error'} when backend returns 400", async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 400 }));
    const result = await verifyEmailAction("bad-token");
    expect(result.status).toBe("error");
  });
});

// =========================================================================
// Schemas (direct unit checks — UX-only mirror)
// =========================================================================

describe("Schemas", () => {
  it("LoginSchema accepts minimum valid shape", () => {
    expect(LoginSchema.safeParse({ email: "a@b.co", password: "x" }).success).toBe(true);
  });

  it("RegisterSchema enforces 12+ chars + upper/lower/digit", () => {
    expect(
      RegisterSchema.safeParse({
        email: "a@b.co",
        password: "alllower-1234",
        confirm_password: "alllower-1234",
      }).success,
    ).toBe(false);
    expect(
      RegisterSchema.safeParse({
        email: "a@b.co",
        password: "Valid-Pass-1234",
        confirm_password: "Valid-Pass-1234",
      }).success,
    ).toBe(true);
  });
});
