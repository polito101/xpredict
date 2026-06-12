import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// next/link → plain anchor; next/navigation usePathname → fixed route (and
// useRouter for the DemoLoginButton the demo branch renders); the auth server
// actions are no-op stubs for the render tests.
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/wallet",
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("@/lib/auth", () => ({
  logoutAction: vi.fn(),
  demoLoginAction: vi.fn(async () => undefined),
}));

import { PlayerNav } from "./player-nav";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("<PlayerNav />", () => {
  // Phase 19: the app destinations live behind auth — they render only when the
  // visitor is authenticated. A logged-out visitor sees the landing chrome.
  test("renders the primary destinations when authenticated", () => {
    render(<PlayerNav isAuthenticated={true} />);
    expect(screen.getByText("Markets")).toBeInTheDocument();
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("Wallet")).toBeInTheDocument();
    expect(screen.getByText("Portfolio")).toBeInTheDocument();
  });

  // LB-B-03 (v1.3 Live-Bets) — the Live destination links to /live. In the
  // Phase 19 redesign the app destinations show only when authenticated.
  test("links the Live destination to /live", () => {
    render(<PlayerNav isAuthenticated={true} />);
    expect(screen.getByText("Live").closest("a")).toHaveAttribute(
      "href",
      "/live",
    );
  });

  test("white-label logged out: Log in / Sign up (no app destinations, no Log out)", () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "");
    render(<PlayerNav isAuthenticated={false} />);
    expect(screen.getByText("Log in")).toBeInTheDocument();
    expect(screen.getByText("Sign up")).toBeInTheDocument();
    expect(screen.queryByText("Log out")).not.toBeInTheDocument();
    expect(screen.queryByText("Markets")).not.toBeInTheDocument();
    expect(screen.queryByText("Wallet")).not.toBeInTheDocument();
  });

  test("demo build logged out: ONE 'Probar la demo' action — no Log in / Sign up (2026-06-11)", () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "true");
    render(<PlayerNav isAuthenticated={false} />);
    expect(
      screen.getByRole("button", { name: /probar la demo/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Log in")).not.toBeInTheDocument();
    expect(screen.queryByText("Sign up")).not.toBeInTheDocument();
  });

  test("shows Log out when logged in, never Log in", () => {
    render(<PlayerNav isAuthenticated={true} />);
    expect(screen.getByText("Log out")).toBeInTheDocument();
    expect(screen.queryByText("Log in")).not.toBeInTheDocument();
  });

  test("marks the current destination with aria-current=page", () => {
    // usePathname is mocked to "/wallet"
    render(<PlayerNav isAuthenticated={true} />);
    expect(screen.getByText("Wallet")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Markets")).not.toHaveAttribute("aria-current", "page");
  });
});
