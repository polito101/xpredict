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
  test("renders the primary destinations", () => {
    render(<PlayerNav isAuthenticated={false} />);
    expect(screen.getByText("Markets")).toBeInTheDocument();
    expect(screen.getByText("Wallet")).toBeInTheDocument();
    expect(screen.getByText("Portfolio")).toBeInTheDocument();
  });

  test("renders the Live destination linking to /live (LB-B-03)", () => {
    render(<PlayerNav isAuthenticated={false} />);
    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("Live").closest("a")).toHaveAttribute("href", "/live");
  });

  test("shows Log in / Sign up when logged out, never Log out", () => {
    render(<PlayerNav isAuthenticated={false} />);
    expect(screen.getByText("Log in")).toBeInTheDocument();
    expect(screen.getByText("Sign up")).toBeInTheDocument();
    expect(screen.queryByText("Log out")).not.toBeInTheDocument();
  });

  test("shows Log out when logged in, never Log in", () => {
    render(<PlayerNav isAuthenticated={true} />);
    expect(screen.getByText("Log out")).toBeInTheDocument();
    expect(screen.queryByText("Log in")).not.toBeInTheDocument();
  });

  test("marks the current destination with aria-current=page", () => {
    // usePathname is mocked to "/wallet"
    render(<PlayerNav isAuthenticated={false} />);
    expect(screen.getByText("Wallet")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Markets")).not.toHaveAttribute("aria-current", "page");
  });
});
