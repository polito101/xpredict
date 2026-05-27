/**
 * Plan 02-05 Task 2 — Admin login form tests.
 *
 * Mirrors Plan 02-04 `login.test.tsx` but exercises the admin surface:
 *   - Mocks `adminLoginAction` from `@/lib/auth`.
 *   - Renders `<AdminLoginForm />` and asserts the admin-specific labels
 *     + the form submission delegates the FormData payload (email +
 *     password) to `adminLoginAction`.
 *   - Asserts the "Invalid credentials" form-level error renders when
 *     the action returns a `_form` error.
 *
 * Runs under `jsdom` (vitest.config.ts matches `*.test.tsx` → jsdom).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the admin Server Action. We use vi.hoisted() so the mock value
// is initialised in time for `vi.mock`'s hoisted factory (Plan 02-04
// inherited pattern — see lib/__tests__/auth.test.ts deviation #2).
const adminLoginActionMock = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<unknown>>(async () => undefined),
);
vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    adminLoginAction: adminLoginActionMock,
  };
});

// Avoid `next/navigation` noise — the action redirects server-side which is
// useless in jsdom.
vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
}));

import { AdminLoginForm } from "../login/admin-login-form";

beforeEach(() => {
  adminLoginActionMock.mockClear();
});

describe("<AdminLoginForm />", () => {
  it("renders_admin_login_form — email + password + 'Sign in as admin' button", () => {
    render(<AdminLoginForm />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    // The button label MUST be admin-distinct to differentiate from the
    // player /login form (success criteria #2 of the plan).
    expect(
      screen.getByRole("button", { name: /sign in as admin/i }),
    ).toBeInTheDocument();
  });

  it("submits_to_admin_action — FormData carries email + password to adminLoginAction", async () => {
    const user = userEvent.setup();
    render(<AdminLoginForm />);
    await user.type(screen.getByLabelText(/email/i), "admin@xpredict.local");
    await user.type(screen.getByLabelText(/password/i), "AdminPass1234!");
    await user.click(screen.getByRole("button", { name: /sign in as admin/i }));

    expect(adminLoginActionMock).toHaveBeenCalled();
    const formData = adminLoginActionMock.mock.calls[0]?.[1] as
      | FormData
      | undefined;
    expect(formData?.get("email")).toBe("admin@xpredict.local");
    expect(formData?.get("password")).toBe("AdminPass1234!");
  });

  it("displays_inline_form_error — surfaces _form errors returned by the action", async () => {
    const user = userEvent.setup();
    adminLoginActionMock.mockResolvedValueOnce({
      errors: { _form: ["Invalid credentials"] },
    });
    render(<AdminLoginForm />);
    await user.type(screen.getByLabelText(/email/i), "admin@xpredict.local");
    await user.type(screen.getByLabelText(/password/i), "wrong-pass");
    await user.click(screen.getByRole("button", { name: /sign in as admin/i }));

    expect(
      await screen.findByText(/invalid credentials/i),
    ).toBeInTheDocument();
  });
});
