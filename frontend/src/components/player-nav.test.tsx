import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// next/link → plain anchor; next/navigation usePathname → fixed route;
// the logout server action is a no-op stub for the render test.
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
vi.mock("next/navigation", () => ({ usePathname: () => "/wallet" }));
vi.mock("@/lib/auth", () => ({ logoutAction: vi.fn() }));

import { PlayerNav } from "./player-nav";

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

  test("shows only Log in / Sign up when logged out (no app destinations, no Log out)", () => {
    render(<PlayerNav isAuthenticated={false} />);
    expect(screen.getByText("Log in")).toBeInTheDocument();
    expect(screen.getByText("Sign up")).toBeInTheDocument();
    expect(screen.queryByText("Log out")).not.toBeInTheDocument();
    expect(screen.queryByText("Markets")).not.toBeInTheDocument();
    expect(screen.queryByText("Wallet")).not.toBeInTheDocument();
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
