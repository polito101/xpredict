/**
 * Plan 02-04 Task 2 — Login form rendering + submission tests.
 *
 * Runs under `jsdom` (vitest.config.ts environmentMatchGlobs picks .tsx).
 *
 * Strategy:
 *   - Mock `next/navigation`'s `redirect()` (server-only sentinel — useless in jsdom).
 *   - Mock the `loginAction` Server Action so the form's `useActionState`
 *     receives a stub instead of a server-side call.
 *   - Render `<LoginForm />` and assert: inputs present, submit button, error display.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the Server Action module BEFORE importing LoginForm. We type the
// mock generically so Vitest's `mockResolvedValueOnce` accepts the full
// ActionState union without TS or next-lint complaining about `any`.
const loginActionMock = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<unknown>>(async () => undefined),
);
vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    loginAction: loginActionMock,
  };
});

// Avoid next/navigation noise.
vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
}));

import { LoginForm } from "../login/login-form";

beforeEach(() => {
  loginActionMock.mockClear();
});

describe("<LoginForm />", () => {
  it("renders email + password inputs and a Sign in button", () => {
    render(<LoginForm />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sign in/i }),
    ).toBeInTheDocument();
  });

  it("invokes loginAction with form data on submit", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "valid-pass-12");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(loginActionMock).toHaveBeenCalled();
    // The action's second arg is the FormData. Pull it out and check the keys.
    const formData = loginActionMock.mock.calls[0]?.[1] as FormData | undefined;
    expect(formData?.get("email")).toBe("user@example.com");
    expect(formData?.get("password")).toBe("valid-pass-12");
  });

  it("displays a form-level error returned by loginAction", async () => {
    const user = userEvent.setup();
    loginActionMock.mockResolvedValueOnce({
      errors: { _form: ["Invalid credentials"] },
    });
    render(<LoginForm />);
    await user.type(screen.getByLabelText(/email/i), "x@y.co");
    await user.type(screen.getByLabelText(/password/i), "any");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/invalid credentials/i)).toBeInTheDocument();
  });
});
