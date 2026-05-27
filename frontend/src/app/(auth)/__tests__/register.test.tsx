/**
 * Plan 02-04 Task 2 — Register form client-side validation tests.
 *
 * Runs under `jsdom`. Asserts that the zod resolver mirrors backend
 * password rules so the form catches obvious mistakes BEFORE the
 * Server Action is invoked (UX-only — backend re-validates).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the Server Action module BEFORE importing RegisterForm. We type the
// mock generically (`(...args: unknown[]) => Promise<unknown>`) so Vitest's
// `mockResolvedValueOnce` accepts the full ActionState union without TS or
// the next-lint eslint rule rejecting it.
const registerActionMock = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<unknown>>(async () => undefined),
);
vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    registerAction: registerActionMock,
  };
});

vi.mock("next/navigation", () => ({ redirect: vi.fn() }));

import { RegisterForm } from "../register/register-form";

beforeEach(() => {
  registerActionMock.mockClear();
});

describe("<RegisterForm />", () => {
  it("blocks submit on a too-short password and displays an error", async () => {
    const user = userEvent.setup();
    render(<RegisterForm />);
    await user.type(screen.getByLabelText(/email/i), "a@b.co");
    await user.type(screen.getByLabelText(/^password/i), "short");
    await user.type(screen.getByLabelText(/confirm password/i), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    // The zod resolver must hold the form back — no Server Action call.
    expect(registerActionMock).not.toHaveBeenCalled();

    expect(
      await screen.findByText(/at least 12 characters/i),
    ).toBeInTheDocument();
  });

  it("shows a 'Passwords must match' error when confirm does not match", async () => {
    const user = userEvent.setup();
    render(<RegisterForm />);
    await user.type(screen.getByLabelText(/email/i), "a@b.co");
    await user.type(screen.getByLabelText(/^password/i), "Valid-Pass-1234");
    await user.type(screen.getByLabelText(/confirm password/i), "Different-1");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(registerActionMock).not.toHaveBeenCalled();
    expect(await screen.findByText(/passwords must match/i)).toBeInTheDocument();
  });
});
