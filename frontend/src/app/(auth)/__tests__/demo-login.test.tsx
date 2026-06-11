/**
 * quick-260611-lcr (DEMO-01) — DemoLoginButton rendering + behaviour tests.
 *
 * Runs under `jsdom`. Strategy mirrors login.test.tsx:
 *   - Mock `demoLoginAction` (the Server Action) so the button's useActionState
 *     receives a stub instead of a real server call.
 *   - Mock `next/navigation`'s `useRouter` so we can assert router.push.
 *
 * The env gate (NEXT_PUBLIC_DEMO_MODE) lives in page.tsx, so the component test
 * does not need the env flag — it tests the button in isolation.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the Server Action module BEFORE importing the component.
const demoLoginActionMock = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<unknown>>(async () => undefined),
);
vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    demoLoginAction: demoLoginActionMock,
  };
});

// Mock next/navigation's useRouter so we can assert navigation.
const pushMock = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  redirect: vi.fn(),
}));

import { DemoLoginButton } from "../login/demo-login-button";

beforeEach(() => {
  demoLoginActionMock.mockClear();
  demoLoginActionMock.mockResolvedValue(undefined);
  pushMock.mockClear();
});

describe("<DemoLoginButton />", () => {
  it("renders a 'Probar la demo' button", () => {
    render(<DemoLoginButton />);
    expect(
      screen.getByRole("button", { name: /probar la demo/i }),
    ).toBeInTheDocument();
  });

  it("invokes demoLoginAction and pushes to /markets on success", async () => {
    const user = userEvent.setup();
    demoLoginActionMock.mockResolvedValueOnce({
      success: true,
      message: "demo-session-started",
    });
    render(<DemoLoginButton />);

    await user.click(screen.getByRole("button", { name: /probar la demo/i }));

    expect(demoLoginActionMock).toHaveBeenCalled();
    // useEffect navigates once the action resolves to a success state.
    await vi.waitFor(() => expect(pushMock).toHaveBeenCalledWith("/markets"));
  });

  it("shows an inline error and does NOT navigate on failure", async () => {
    const user = userEvent.setup();
    demoLoginActionMock.mockResolvedValueOnce({
      errors: { _form: ["No se pudo iniciar la demo. Inténtalo de nuevo."] },
    });
    render(<DemoLoginButton />);

    await user.click(screen.getByRole("button", { name: /probar la demo/i }));

    expect(await screen.findByTestId("demo-error")).toHaveTextContent(
      /no se pudo iniciar la demo/i,
    );
    expect(pushMock).not.toHaveBeenCalled();
  });
});
