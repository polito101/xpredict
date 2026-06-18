import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// next/link → plain anchor; next/navigation usePathname → fixed admin route;
// the admin logout Server Action is a no-op stub for the render tests (mirrors
// player-nav.test.tsx, which stubs logoutAction the same way).
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
  usePathname: () => "/admin/users",
}));
vi.mock("@/lib/auth", () => ({
  adminLogoutAction: vi.fn(),
}));

import { AdminNav } from "./admin-nav";

describe("<AdminNav />", () => {
  test("renders the admin destinations", () => {
    render(<AdminNav />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.getByText("Markets")).toBeInTheDocument();
    expect(screen.getByText("Events")).toBeInTheDocument();
    expect(screen.getByText("Audit log")).toBeInTheDocument();
    expect(screen.getByText("Branding")).toBeInTheDocument();
  });

  test("marks the current destination with aria-current=page", () => {
    // usePathname is mocked to "/admin/users"
    render(<AdminNav />);
    expect(screen.getByText("Users")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Dashboard")).not.toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  // Regression — the admin logout fix. "Log out" must terminate the admin
  // session via the adminLogoutAction Server Action (revokes the Bearer +
  // clears admin_jwt), NOT navigate to /admin/logout — a route that does not
  // exist (404) and never logs the admin out.
  test("renders Log out as a Server Action form submit, not a dead /admin/logout link", () => {
    render(<AdminNav />);
    const logout = screen.getByText("Log out");
    expect(logout.tagName).toBe("BUTTON");
    expect(logout).toHaveAttribute("type", "submit");
    expect(logout.closest("form")).toBeInTheDocument();
    // The old dead link must be gone.
    expect(
      screen.queryByRole("link", { name: "Log out" }),
    ).not.toBeInTheDocument();
    expect(document.querySelector('a[href="/admin/logout"]')).toBeNull();
  });
});
